# Image Highlighting Feature

**Status**: Completed  
**Date**: December 17, 2025  
**Commits**: 
- e480ed14b2821daedab57f18e9948240bb3e4e64 (Core foundation)
- b2f9d22e8026a6bea2f5dcb03c91f2c695cc1142 (Archived approach - separate image storage)
- b94cdfabdf7068b22f92f8323e50af487cecbe1b (Final implementation - client-side rendering)

## Overview

Users can now upload images as part of their exercise submissions. When the AI tutor identifies a specific part of the student's work that contains a mistake, it can highlight that text region directly on the user's uploaded image. The highlighted image is then displayed in the exercise chat interface.

## Implementation Details

### Architecture

The feature uses a **two-stage highlighting approach**:

1. **Detection Stage (AI)**
   - LLM identifies the problematic text and returns it in the `text_to_highlight` field
   - `find_text_in_image()` calls Gemini's vision API to locate that exact text in the student's image
   - Gemini returns a bounding box in normalized format (0-1000 range, format: `[y0, x0, y1, x1]`)

2. **Storage Stage (Backend)**
   - Bounding box is converted from normalized coordinates to pixel coordinates via `treat_gemini_bbox()`
   - Coordinates are stored in the `TraceImage.highlight_bboxes` JSONField (not as a separate image)
   - Original user-uploaded image remains unmodified in storage

3. **Rendering Stage (Frontend/Backend-on-demand)**
   - When displaying the image, the system checks if `highlight_bboxes` exist
   - If highlights exist, the `serve_highlighted_image()` endpoint applies all stored bboxes to the original
   - The highlighted version is served on-demand without permanently modifying storage
   - Frontend displays the highlighted image URL instead of the original

### Key Components

#### Backend - `exercises/highlight.py`

**`add_highlighter(img, bounding_box, color="yellow", margin=[5, 10])`**
- Adds a semi-transparent colored rectangle with rounded corners to a PIL Image
- Creates a "stabylo/highlighter marker" visual effect
- Supports custom colors and configurable margins around the bbox
- Returns the modified PIL Image

**`treat_gemini_bbox(bbox, img_size)`**
- Converts Gemini's normalized bounding box format to pixel coordinates
- Input: `[y0, x0, y1, x1]` normalized to 0-1000 range
- Output: `[x0, y0, x1, y1]` in actual pixel coordinates
- Handles image height/width to properly denormalize

#### Backend - `exercises/logic.py`

**`find_text_in_image(text_to_find, img_bytes, img_mime_type)`**
- Calls Gemini's vision API with the image and target text as input
- Returns a dict with:
  - `bounding_box`: `[y0, x0, y1, x1]` or empty list if not found
  - `comment`: Error message or empty string
  - `elapsed_time`: API call duration for performance monitoring
- Includes error handling for missing images or text not found

**Highlighting logic in `fetch_ai_guidance()`**
- Runs after all TraceImage objects are linked to the Trace
- Only activates if `TOGGLE_HIGHLIGHT` is True and `text_to_highlight` exists
- Flow:
  1. Retrieves image bytes from first uploaded image
  2. Calls `find_text_in_image()` to get bbox
  3. Normalizes bbox coordinates with `treat_gemini_bbox()`
  4. Stores bbox in `TraceImage.highlight_bboxes` as JSON
  5. Logs all steps for debugging

#### Backend - `exercises/views_image_upload.py`

**`serve_highlighted_image(token)`**
- New endpoint: `/exercises/image-highlighted/<token>/`
- Loads the original image from TraceImage
- Iterates through all entries in `highlight_bboxes` and applies highlights in order
- Returns a JPEG with all highlights applied (generated on each request, not cached)
- Includes authorization checks (ownership or teacher role)
- Falls back to original image if no highlights exist

#### Database Model - `exercises/models.py`

**TraceImage changes**
- **Removed**: `image_source` field (from failed approach)
- **Added**: `highlight_bboxes` JSONField
  - Default: empty list `[]`
  - Format: `[{'bbox': [x0, y0, x1, y1], 'color': 'yellow'}, ...]`
  - Allows multiple highlights on same image
  - Each entry includes color for future styling flexibility

#### Frontend - `ChatbotPanel.ts`

**`getImageUrl(img)`**
- Helper method to determine correct image endpoint
- If `img.has_highlights` is true → `/exercises/image-highlighted/<token>`
- Otherwise → `/exercises/image/<token>` (original image)
- Integrated into user message display

**User message images**
- Images now include `has_highlights` boolean flag
- Only highlights in user's original submission are shown (not separate assistant images)

#### Frontend - `mobile_chat.ts`

**`normalizeImages(images)`**
- Helper function to convert various image formats to consistent structure
- Handles both local blob URLs and remote server URLs
- Applies correct endpoint based on `has_highlights` flag
- Supports the unified image display model

**Image update logic**
- Server returns updated images with token and highlight info
- Frontend replaces local blob URLs with server URLs
- Properly cleans up blob URLs to prevent memory leaks

#### Frontend - URL Routes

**New route added in `exercises/urls.py`**
```
path('image-highlighted/<str:token>/', views_image_upload.serve_highlighted_image, name='serve_highlighted_image')
```

### Data Flow

```
Student uploads image
    ↓
Student receives feedback
    ↓
Tutor response includes text_to_highlight
    ↓
find_text_in_image(text, image_bytes) → Gemini API → bbox [y0,x0,y1,x1] (0-1000)
    ↓
treat_gemini_bbox(bbox, img_size) → [x0, y0, x1, y1] (pixels)
    ↓
Store in TraceImage.highlight_bboxes as JSON
    ↓
Frontend requests image display
    ↓
Check if image has highlights
    ↓
If yes: serve_highlighted_image(token) → apply bboxes → return JPEG
If no: serve_trace_image(token) → return original
    ↓
Display in chat interface
```

### Configuration

**`TOGGLE_HIGHLIGHT` flag in `logic.py`**
- Currently set to `True` (feature enabled)
- Can be toggled to disable highlighting without code changes
- Prevents highlighting from running if disabled

### Error Handling

The implementation includes comprehensive error handling:
- If Gemini can't find the text → empty bbox, logged as warning
- If image bytes are missing → caught and logged, continues gracefully
- If highlight rendering fails → falls back to original image
- If authorization fails → returns 403 Forbidden

### Design Evolution

The feature went through two approaches before the final implementation:

1. **Approach 1 (Abandoned - Commit 2)**
   - Stored highlighted image as separate `TraceImage` object
   - Marked images with `image_source` field ('user_upload' vs 'assistant_generated')
   - Displayed as separate section in assistant response
   - **Issue**: More storage, separate image management complexity

2. **Approach 2 (Final - Commit 3)**
   - Store only bbox coordinates in original image metadata
   - Render highlights on-demand via `serve_highlighted_image()`
   - Display as the user's image with highlights applied
   - **Benefits**: Storage efficient, single image to manage, flexible styling

### Performance Considerations

- **Highlight rendering**: Happens on-demand (first request may be slightly slower)
- **Gemini API call**: Adds ~1-2 seconds to tutor response time
- **Image quality**: Highlights saved at 85% JPEG quality (imperceptible quality loss, ~30% size savings in failed approach)
- **Authorization checks**: Minimal overhead, only on highlight endpoint

## Testing Notes

- Feature is controlled by `TOGGLE_HIGHLIGHT` flag for easy testing
- Supports multiple highlights per image (though typically only one is used)
- Works with all exercise types that support image uploads
- Both desktop and mobile interfaces supported

## Future Improvements

- Cache rendered highlighted images to reduce computation
- Allow customization of highlight color per-response
- Support multiple highlight regions in one response
- Add visual indicators showing which part of the image was highlighted
