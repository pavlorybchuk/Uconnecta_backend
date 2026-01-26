from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os

User = get_user_model()

class Command(BaseCommand):
    help = "Create superuser if not exists"

    def handle(self, *args, **options):
        email = os.getenv("DJANGO_SUPERUSER_EMAIL")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        username = os.getenv("DJANGO_SUPERUSER_USERNAME")

        if not all([email, password, username]):
            self.stdout.write("Superuser env vars not set, skipping")
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write("Superuser already exists")
            return

        User.objects.create_superuser(
            email=email,
            username=username,
            phone="0000000000",
            password=password,
        )
        self.stdout.write("Superuser created")