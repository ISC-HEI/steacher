from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q


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
        return (self.username or "").strip()

    @property
    def display_name(self) -> str:
        return self.get_display_name()



    def clean(self):
        """Enforce security invariants on staff/superuser flags at the model layer.

        Rules:
        - Only superuser may be staff, and superuser must be staff → flags are equal.
        - The application never promotes users via web forms; this is additionally enforced in admin.
        """
        super().clean()
        # Normalize invariants: is_staff must always equal is_superuser
        if getattr(self, 'is_staff', False) != getattr(self, 'is_superuser', False):
            # Raise a clear error to block any attempt from the web layer
            raise ValidationError({
                'is_staff': 'is_staff must equal is_superuser (non-superusers cannot be staff).',
                'is_superuser': 'is_superuser must equal is_staff.'
            })

    def save(self, *args, **kwargs):
        # Validate before saving so web requests cannot bypass .clean()
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [
            # Allow at most one superuser in the system (partial unique index on True)
            models.UniqueConstraint(
                fields=["is_superuser"],
                condition=Q(is_superuser=True),
                name="unique_single_superuser",
            ),
            # Non-superusers may not be staff
            models.CheckConstraint(
                check=Q(is_staff=False) | Q(is_superuser=True),
                name="non_superuser_cannot_be_staff",
            ),
            # Superuser must be staff (keeps flags equal and admin usable)
            models.CheckConstraint(
                check=Q(is_superuser=False) | Q(is_staff=True),
                name="superuser_must_be_staff",
            ),
        ]

