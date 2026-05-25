import os
import zipfile
import logging
import requests
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

# Configuration parameters for the recognition service retrieved from environment variables
RECOGNITION_BASE_URL = os.getenv("RECOGNITION_BASE_URL")
RECOGNITION_FIELD = "file"
RECOGNITION_API_KEY = os.getenv("RECOGNITION_API_KEY")
RECOGNITION_AUTH_HEADER = "X-Api-Key"
RECOGNITION_TIMEOUT = (5, 30)


class RecognizePhotoView(APIView):
    """
    API View to handle processing and recognition of vehicle/plate photos uploaded inside a ZIP archive.
    Accepts multipart form-data containing the ZIP file.
    """
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """
        Handles POST request to validate the uploaded ZIP archive, extract the image,
        forward it to the external recognition endpoint, and return the parsed response json.
        """
        zip_file = request.FILES.get("file")
        if not zip_file:
            return Response(
                {"detail": "No file provided. Send a ZIP as multipart field 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not zip_file.name.lower().endswith(".zip"):
            return Response(
                {"detail": "Expected a .zip archive."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            image_name, image_bytes = _extract_image_from_zip(zip_file)
        except _ZipError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("Unexpected error while reading ZIP archive")
            return Response(
                {"detail": "Failed to read the ZIP archive."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ext_response = _call_recognition_api(image_name, image_bytes)
        except requests.Timeout:
            logger.error("Recognition API timed out after %ss", RECOGNITION_TIMEOUT)
            return Response(
                {"detail": "Recognition service timed out. Please try again."},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except requests.ConnectionError:
            logger.error("Could not connect to recognition API at %s", RECOGNITION_BASE_URL)
            return Response(
                {"detail": "Recognition service is unavailable."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except requests.RequestException as exc:
            logger.exception("Recognition API request failed")
            return Response(
                {"detail": f"Recognition service error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if not ext_response.ok:
            logger.error(
                "Recognition API returned %s: %s",
                ext_response.status_code,
                ext_response.text[:200],
            )
            return Response(
                {
                    "detail": "Recognition service returned an error.",
                    "upstream_status": ext_response.status_code,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        try:
            result = ext_response.json()
        except ValueError:
            result = {"raw": ext_response.text.strip()}

        return Response(result, status=status.HTTP_200_OK)


# Supported static extensions for filtering images inside the archive
_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


class _ZipError(ValueError):
    """
    Custom Exception raised when the uploaded archive is malformed or contains no usable image file format.
    """


def _extract_image_from_zip(zip_file):
    """
    Helper function to open a ZIP file stream, extract the first valid target image entry,
    and skip OS system-generated folders like __MACOSX.
    """
    try:
        zf = zipfile.ZipFile(zip_file)
    except zipfile.BadZipFile:
        raise _ZipError("The uploaded file is not a valid ZIP archive.")

    image_entries = [
        name for name in zf.namelist()
        if not name.startswith("__MACOSX")
        and not name.endswith("/")
        and any(name.lower().endswith(ext) for ext in _ALLOWED_IMAGE_EXTENSIONS)
    ]

    if not image_entries:
        raise _ZipError("ZIP archive contains no supported image.")

    entry_name = image_entries[0]

    image_file = zf.open(entry_name)

    bare_name = entry_name.split("/")[-1]
    return bare_name, image_file


def _call_recognition_api(image_name: str, image_file):
    """
    Helper function to perform a multi-part file request to the external computer vision service,
    injecting authentication keys and appropriate image mime types dynamically.
    """

    ext = image_name.rsplit(".", 1)[-1].lower()
    mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"

    headers = {"ngrok-skip-browser-warning": "true"}

    if RECOGNITION_API_KEY:
        headers[RECOGNITION_AUTH_HEADER] = RECOGNITION_API_KEY

    return requests.post(
        RECOGNITION_BASE_URL,
        files={
            RECOGNITION_FIELD: (
                image_name,
                image_file,
                mime,
            )
        },
        headers=headers,
        timeout=RECOGNITION_TIMEOUT,
    )
