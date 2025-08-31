from typing import Optional

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authenticate with either email (case-insensitive) or username.
    Keeps default permission checks via ModelBackend.
    """

    def authenticate(self, request, username: Optional[str] = None, password: Optional[str] = None, **kwargs):
        if username is None or password is None:
            return None

        UserModel = get_user_model()
        candidate = None

        # First try matching by email (case-insensitive)
        try:
            candidate = UserModel.objects.get(email__iexact=username.strip())
        except UserModel.DoesNotExist:
            # Fallback to username (exact)
            try:
                candidate = UserModel.objects.get(username=username)
            except UserModel.DoesNotExist:
                return None

        if candidate and candidate.check_password(password) and self.user_can_authenticate(candidate):
            return candidate
        return None


