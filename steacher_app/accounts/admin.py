from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django import forms
from django.db import IntegrityError

from .models import User
from exercises.models import CohortMembership, CourseMembership


class CohortMembershipInline(admin.TabularInline):
    model = CohortMembership
    fk_name = 'user'
    extra = 0
    autocomplete_fields = ['cohort']
    fields = ('cohort', 'role', 'status', 'joined_at', 'added_by')
    readonly_fields = ('joined_at',)
    verbose_name = 'Cohort membership'
    verbose_name_plural = 'Cohort memberships'


class CourseMembershipInline(admin.TabularInline):
    model = CourseMembership
    fk_name = 'user'
    extra = 0
    autocomplete_fields = ['course']
    fields = ('course', 'role', 'joined_at', 'added_by')
    readonly_fields = ('joined_at',)
    verbose_name = 'Course membership'
    verbose_name_plural = 'Course memberships'


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
    inlines = [CohortMembershipInline, CourseMembershipInline]

    def get_readonly_fields(self, request, obj=None):
        # Prevent any attempt to toggle staff/superuser via admin UI
        readonly = super().get_readonly_fields(request, obj) or ()
        return tuple(set(readonly) | {"is_staff", "is_superuser"})

    def save_formset(self, request, form, formset, change):
        try:
            instances = formset.save(commit=False)
            # Process deletions first
            for obj in getattr(formset, 'deleted_objects', []):
                try:
                    obj.delete()
                except Exception:
                    continue
            for obj in instances:
                if isinstance(obj, (CohortMembership, CourseMembership)) and not getattr(obj, 'added_by_id', None):
                    obj.added_by = request.user
                obj.save()
            formset.save_m2m()
        except IntegrityError:
            # Handle unique owner constraints on course/cohort
            raise forms.ValidationError('Only one owner is allowed per course/cohort. Demote the existing owner before assigning a new one.')


