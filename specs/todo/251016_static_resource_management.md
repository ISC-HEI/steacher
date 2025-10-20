# Static Resource Management & Cache-Busting

**Date:** 2025-10-16  
**Status:** Implemented

## Overview

We use Django's `ManifestStaticFilesStorage` to implement cache-busting for static files in production. This ensures browsers always load the latest version of JavaScript, CSS, and other static assets when they change, while allowing aggressive browser caching for performance.

## How It Works

### Development (DEBUG=True)
- Static files served directly from `static/` directory
- No hashing applied
- Fast iteration during development
- Files accessed as: `/static/js/dist/python.js`

### Production (DEBUG=False)
1. **Build Process:** TypeScript/frontend assets compiled to `static/js/dist/`
2. **Collectstatic:** `manage.py collectstatic` gathers all static files and:
   - Calculates content hash for each file (MD5)
   - Generates hashed filenames: `python.js` → `python.7b8e28adc2b7.js`
   - Copies files to `staticfiles/` directory with both original and hashed names
   - Creates `staticfiles.json` manifest mapping original → hashed names
3. **Template Resolution:** `{% static 'js/dist/python.js' %}` automatically resolves to hashed URL in production
4. **Nginx Serves:** Files from `/app/staticfiles/` with aggressive caching headers

### Why Duplication?

Yes, we have two copies of static files in production:
- **Original:** `static/js/dist/python.js`
- **Hashed:** `staticfiles/js/dist/python.7b8e28adc2b7.js`

This is Django's standard pattern. The duplication exists because `collectstatic` is designed to:
- Gather files from multiple sources (apps, node_modules, etc.)
- Process them all in one place
- Generate a single manifest

Trade-off: Disk space (~10MB duplicated) vs. proper cache invalidation. We choose proper caching.

## Implementation Details

### Custom Storage Backend

**File:** `exercises/storage.py`

```python
class ForgivingManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """Doesn't fail on missing source maps from node_modules."""
```

This custom storage extends Django's built-in storage to gracefully handle missing `.js.map` files that node_modules packages reference but don't always include. Without this, collectstatic would crash.

### Settings Configuration

**File:** `exam_project/settings.py`

```python
STORAGES = {
    "staticfiles": {
        "BACKEND": "exercises.storage.ForgivingManifestStaticFilesStorage",
    },
}
```

### Docker Build

**File:** `Dockerfile`

```dockerfile
RUN python manage.py collectstatic --noinput
```

Runs during image build, before deployment.

### Nginx Configuration

**File:** `nginx/nginx.conf`

```nginx
location /static/ {
    alias /app/staticfiles/;
    expires 1y;
    access_log off;
    add_header Cache-Control "public, immutable";
}
```

Serves from collectstatic output directory with:
- 1-year expiration header
- `immutable` flag (tells browser file will never change at this URL)
- No access logging for performance

## Cache-Busting Behavior

When you update `python.js`:
1. Content changes → hash changes
2. New filename: `python.7b8e28adc2b7.js` → `python.a1b2c3d4e5f6.js`
3. Templates resolve to new URL
4. Browser sees new URL → fetches fresh file
5. Old hashed file can stay cached forever (harmless)

## Important Notes

- **All templates must use `{% static %}` tag** - Hard-coded paths won't get hashed URLs
- **CDN files not affected** - This only applies to locally-served static files
- **Import maps handle hashing** - Module imports in templates use `{% static %}` inside import maps
- **No .mjs files locally** - We only have `.js` files; `.mjs` references are CDN-only

## Files Modified

- `steacher_app/exam_project/settings.py` - Added STORAGES config
- `steacher_app/exercises/storage.py` - Created custom storage backend
- `steacher_app/Dockerfile` - Added collectstatic step
- `nginx/nginx.conf` - Updated static location and removed obsolete .mjs rule

