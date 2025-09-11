from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "preferred_language")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "preferred_language", "password1", "password2"),
            },
        ),
    )
    list_display = ("username", "email", "first_name", "last_name", "preferred_language")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)

    def get_readonly_fields(self, request, obj=None):
        # Prevent any attempt to toggle staff/superuser via admin UI
        readonly = super().get_readonly_fields(request, obj) or ()
        return tuple(set(readonly) | {"is_staff", "is_superuser"})


