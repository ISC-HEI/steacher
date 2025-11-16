# Image Upload Feature for Open Question Exercises

**Date:** 2024-11-16  
**Status:** ✅ Completed  
**Exercise Type:** Open Question (extensible to other types)

## Overview

This specification documents the complete image upload feature for exercises, allowing students to submit handwritten work or other visual materials as part of their answers. The system supports multiple images per submission (up to 3), integrates with Gemini's vision capabilities, and persists images as part of conversation history.

## Problem Statement

### Original Issues
1. **Images disappeared on page refresh** - Images were stored in local frontend state but not properly linked to traces in the database
2. **No persistence** - Uploaded images were lost when the page reloaded
3. **Missing history display** - Historical images from previous submissions were not shown in the conversation panel

### Requirements
- Students should be able to upload images via QR code (mobile device)
- Support multiple images per submission (capped at 3)
- Images should persist across page refreshes
- Images should appear in conversation history alongside text
- Images should be sent to the LLM (Gemini) for analysis
- Clean, intuitive UI with vertical stacking of images

## Architecture

### Data Model

**TraceImage Model** (already existed, enhanced usage):
- Stores binary image data in database
- Linked to Trace via foreign key (nullable for upload flow)
- Unique upload token for QR-based upload
- Stores MIME type, file size, and timestamps
- Token has expiry timestamp for security

**Key Relationships:**
- `TraceImage.trace` → `Trace` (many-to-one)
- `Trace.images` → `TraceImage[]` (one-to-many via `related_name='images'`)

### Upload Flow

```
┌─────────────┐
│   Desktop   │
│   Student   │
└──────┬──────┘
       │
       │ 1. Click "Upload picture"
       ▼
┌─────────────────┐
│ Generate Token  │ ← TraceImage created with trace=NULL
│  & QR Code      │
└──────┬──────────┘
       │
       │ 2. Scan QR code
       ▼
┌─────────────────┐
│ Mobile Upload   │
│   (Public)      │ ← Image saved to TraceImage.image
└──────┬──────────┘
       │
       │ 3. Poll for completion
       ▼
┌─────────────────┐
│ Show Preview    │ ← pendingImages array
│  (Desktop)      │
└──────┬──────────┘
       │
       │ 4. Submit answer
       ▼
┌─────────────────┐
│ Create Trace    │
│ Link Images     │ ← TraceImage.trace = created_trace
└──────┬──────────┘
       │
       │ 5. Page refresh
       ▼
┌─────────────────┐
│ Load History    │ ← Serialize trace.images.all()
│ Display Images  │
└─────────────────┘
```

## Implementation Details

### Frontend Components

#### 1. Data Structures (`open_question.ts`)

**PendingImage Interface:**
- Stores upload token (maps to TraceImage.upload_token)
- Stores image URL for preview display

**State Management:**
- `pendingImages` array tracks images awaiting submission
- Starts empty on page load
- Images added after successful QR upload
- Cleared after successful submission
- Individual removal via `removePendingImage(index)` method

#### 2. UI Components (`open_question.html`)

**Upload Button:**
- Only visible when under 3-image limit
- Text changes: "Upload a picture" → "Upload another picture"
- Disabled during AI processing

**Image Preview:**
- Vertical stack of all pending images
- Each image has individual remove button (X)
- Max height 200px per image

**Dynamic Textarea:**
- 10 rows when no images
- 3 rows when images present

**Submit Button:**
- Enabled with images OR text (not both required)
- Disabled during loading state

### Backend Components

#### 1. Payload Structure (`open_question.ts` → `views_students.py`)

**Submission includes:**
- Action type (submit_answer, ask_hint, etc.)
- Text answer
- Array of image tokens

#### 2. Image Processing (`logic.py` - `fetch_ai_guidance()`)

**Loading Images for LLM:**
- Fetches TraceImage objects by token
- Converts binary data to Gemini Part objects
- Appends to user message for LLM
- Keeps references for later trace linking

**Linking to Trace:**
- After trace creation, links all images to the trace
- Updates TraceImage.trace foreign key
- Single save per image with update_fields optimization
- Logs count of linked images

#### 3. History Serialization (`views_students.py` - exercise detail view)

**Loading Images with Traces:**
- Queries all traces with related images
- Serializes images as array of tokens
- Orders images by upload time
- Includes in user_submission data structure for frontend

### Display in Conversation History

#### ChatbotPanel Component (`ChatbotPanel.ts`)

**Inline Image Display:**
- Images display below user message text
- Horizontal layout with gap between images
- Max 120px height thumbnails
- Clickable to enlarge

**Click-to-Enlarge Modal:**
- Full-screen modal overlay
- Image scaled to 90vh max height
- Close on background click or X button
- Managed via `showImageModal` and `modalImageUrl` state

## API Endpoints

### Image Upload Flow

1. **Generate Token:** `POST /exercises/image/upload-token/`
   - Creates `TraceImage` with unique token
   - Returns QR code and upload URL
   - Rate limited: 5 requests/minute per user

2. **Mobile Upload Page:** `GET /exercises/upload/{token}/`
   - Public endpoint (no auth required)
   - Validates token and expiry
   - Renders mobile-friendly upload UI

3. **Submit Image:** `POST /exercises/upload/{token}/submit/`
   - Public endpoint (CSRF exempt)
   - Accepts multipart/form-data
   - Resizes and optimizes image
   - Max size: 30MB input, resized to 2048x800

4. **Check Status:** `GET /exercises/image/image-status/{token}/`
   - Authenticated endpoint
   - Returns `{'status': 'pending'|'completed'|'expired'}`
   - Used for polling from desktop

5. **Serve Image:** `GET /exercises/image/{token}`
   - Authenticated endpoint
   - Serves binary image data
   - Returns appropriate MIME type

## Security Considerations

### Token Expiry
- Upload tokens expire after 10 minutes
- Prevents stale QR codes from being used
- Checked on both upload page and submission

### Authentication
- Token generation: Requires login
- Mobile upload: Public (token serves as auth)
- Image viewing: Requires login
- Status polling: Requires login

### Rate Limiting
- Token generation: 5 per minute per user
- Prevents abuse of upload system

### File Validation
- Input: Max 30MB, must be image MIME type
- Output: Resized to max 2048x800, optimized
- Supports: JPEG, PNG, HEIF, WebP, GIF
- Transparency preserved where possible

## User Experience

### Upload Limits
- **Maximum images per submission:** 3
- **Rationale:** Balance between flexibility and performance
- **UI behavior:** Button disappears at limit, reappears when image removed

### Visual Feedback

**States:**
1. **No images:** "Upload a picture of your answer"
2. **1-2 images:** "Upload another picture" + stacked preview
3. **3 images:** Button hidden, all images previewed
4. **Uploading:** "Waiting for upload..." with progress indicator
5. **Success:** Image added to stack immediately

### Responsive Behavior
- **Textarea:** Shrinks from 10 rows to 3 rows when images present
- **Submit button:** Enabled with images OR text (not both required)
- **Remove buttons:** Individual X button on each preview
- **All interactions disabled** while AI is processing

## Testing Scenarios

### Happy Path
1. ✅ Upload 1 image → preview shows → submit → appears in history
2. ✅ Upload 3 images → button disappears → submit → all in history
3. ✅ Remove middle image → button reappears → can upload again
4. ✅ Submit with only images (no text) → works
5. ✅ Submit with only text (no images) → works
6. ✅ Page refresh → images persist in conversation history

### Edge Cases
1. ✅ Token expiry → shows "Upload link expired"
2. ✅ Upload failure → keeps existing images, shows error
3. ✅ Close modal mid-upload → token expires, no harm
4. ✅ Remove all images → back to initial state
5. ✅ Rapid clicking → disabled during loading state
6. ✅ Multiple images ordered → displayed by upload time

### Error Handling
1. ✅ Network failure during upload → error message, retry possible
2. ✅ Invalid image format → rejected at client
3. ✅ File too large → rejected with message
4. ✅ Token not found → 404 response
5. ✅ Image missing in TraceImage → warning logged, skipped

## Performance Considerations

### Database Optimization
- **Single query per image:** Fetch once, reuse for LLM and trace linking
- **Ordered query:** `tr.images.order_by('uploaded_at')` for consistent display
- **Selective loading:** Only load images for visible traces

### Image Processing
- **Resize on upload:** Max 2048x800 preserves quality while reducing size
- **Binary storage:** Images stored in database (PostgreSQL bytea)
- **MIME type preservation:** Maintains original format when possible
- **Optimization:** Pillow optimize flag reduces file size

### Frontend Efficiency
- **Polling interval:** 2 seconds (balance between responsiveness and load)
- **Auto-stop polling:** Stops on success or modal close
- **Preview URLs:** Use serve endpoint, avoid base64 bloat

## Future Enhancements

### Potential Improvements (Not Implemented)
1. **LaTeX conversion:** Extract handwritten math to LaTeX (mentioned as future TODO)
2. **Image annotation:** Allow students to draw on images before submission
3. **Compression options:** Student choice of quality vs. size
4. **Thumbnail generation:** Separate small thumbnails for history
5. **Batch upload:** Multiple files from PC at once
6. **Exercise-specific limits:** Different max images per exercise type
7. **OCR integration:** Extract text from images automatically

## Files Modified

### Frontend
- `frontend/open_question.ts` (85 lines changed)
- `templates/exercises/students/open_question.html` (45 lines changed)
- `frontend/ChatbotPanel.ts` (35 lines changed)

### Backend
- `exercises/logic.py` (25 lines changed)
- `exercises/views_students.py` (5 lines changed)
- `exercises/views_image_upload.py` (existing, no changes)

### No Changes Required
- Database schema (TraceImage model already existed)
- URL routing (endpoints already existed)
- Models (no migrations needed)

## Configuration

### Required Settings
- No new Django settings required
- Uses existing database configuration (PostgreSQL)
- Uses existing CORS settings for API calls

### Environment Variables
- `GEMINI_API_KEY` - Required for LLM with vision capabilities

## Deployment Notes

### No Special Deployment Steps
- TypeScript auto-compiles via `npm run watch`
- No database migrations needed
- No new dependencies
- Backward compatible with existing exercises

### Verification Checklist
- [ ] Gemini API key configured
- [ ] Image serve endpoint accessible
- [ ] Mobile upload page loads on phones
- [ ] QR code generation works
- [ ] File upload size limits configured in nginx/uwsgi

## Conclusion

The image upload feature is fully integrated into the exercise workflow, providing students with a seamless way to submit visual work. The implementation prioritizes data persistence, clean UX, and efficient resource usage while maintaining security and performance standards.

**Key Success Metrics:**
- ✅ Images persist across sessions
- ✅ Gemini receives and analyzes images
- ✅ Clean, intuitive multi-image UI
- ✅ No performance degradation
- ✅ Zero database migrations required
- ✅ Fully backward compatible

