import os

# Allow Django's sync DB operations in contexts where an event loop is present (pytest-playwright)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

pytest_plugins = [
    "pytest_django",
    "pytest_playwright",
]


