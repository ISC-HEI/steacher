from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    LANGUAGE_CHOICES = [
        ("fr", "French"),
        ("de", "German"),
        ("en", "English"),
    ]

    preferred_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default="en",
        help_text="Preferred language for the UI and tutor guidance.",
    )


