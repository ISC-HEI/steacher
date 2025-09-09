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

    def get_display_name(self) -> str:
        """Return a human-friendly name: "Last, First", or whichever parts exist; fallback to username."""
        last = (self.last_name or "").strip()
        first = (self.first_name or "").strip()
        if last and first:
            return f"{last}, {first}"
        if last:
            return last
        if first:
            return first
        return (self.username or "").strip()

    @property
    def display_name(self) -> str:
        return self.get_display_name()


