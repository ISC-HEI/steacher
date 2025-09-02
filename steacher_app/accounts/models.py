from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("teacher", "Teacher"),
        ("admin", "Admin"),
    ]

    LANGUAGE_CHOICES = [
        ("fr", "French"),
        ("de", "German"),
        ("en", "English"),
    ]

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="student",
        help_text="Application role: student, teacher, or admin.",
    )

    preferred_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default="en",
        help_text="Preferred language for the UI and tutor guidance.",
    )


