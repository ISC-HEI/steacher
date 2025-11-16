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

**TraceImage Model**:
- Stores binary image data in database
- Linked to Trace via foreign key (nullable for upload flow)
- Unique upload token for QR-based upload
- Stores MIME type, file size, and timestamps
- Token has expiry timestamp for security (10 minutes)
- Token chaining fields:
  - `next_token`: CharField storing the upload token for the next image in the chain
  - `chain_position`: IntegerField (0=first, 1=second, 2=third) tracking position in upload sequence
  - Enables sequential multi-image upload from mobile device without desktop interaction

**Key Relationships:**
- `TraceImage.trace` → `Trace` (many-to-one)
- `Trace.images` → `TraceImage[]` (one-to-many via `related_name='images'`)

### Upload Flow

**Standard Flow (Desktop → Mobile → Desktop):**

```
┌─────────────┐
│   Desktop   │
│   Student   │
└──────┬──────┘
       │
       │ 1. Click "Upload picture"
       ▼
┌─────────────────┐
│ Generate Token  │ ← TraceImage created with trace=NULL, chain_position=0
│  & QR Code      │
└──────┬──────────┘
       │
       │ 2. Scan QR code
       ▼
┌─────────────────┐
│ Mobile Upload   │
│   (Public)      │ ← Image saved to TraceImage.image
│  with Cropper   │    next_token generated if chain_position < 2
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
│ Link Images     │ ← TraceImage.trace = created_trace (for all chain positions)
└──────┬──────────┘
       │
       │ 5. Page refresh
       ▼
┌─────────────────┐
│ Load History    │ ← Serialize trace.images.all()
│ Display Images  │
└─────────────────┘
```

**Token Chaining Flow (Mobile-only multi-upload):**

```
┌─────────────────┐
│ Mobile Upload   │ chain_position=0
│   (Photo 1)     │
└──────┬──────────┘
       │ Server returns next_token
       ▼
┌─────────────────┐
│ Mobile Upload   │ chain_position=1
│   (Photo 2)     │ ← Same mobile session continues
└──────┬──────────┘
       │ Server returns next_token
       ▼
┌─────────────────┐
│ Mobile Upload   │ chain_position=2
│   (Photo 3)     │ ← Same mobile session continues
└──────┬──────────┘
       │ No next_token (limit reached)
       ▼
┌─────────────────┐
│   All Done!     │
│ Return to PC    │
└─────────────────┘
```

**Key Benefits:**
- Student can capture all 3 images from phone without returning to desktop
- Modal closes automatically on desktop after first upload
- Desktop continues polling silently for subsequent images
- Chain is linked by parent.next_token → child.upload_token relationship

## Implementation Details

### Frontend Components

#### 1. Mobile Upload UI (`mobile_upload.html`)

**Complete UX Overhaul:**

The mobile upload page is designed to be a standalone single-page app with three states:

**Waiting State:**
- Branded landing page with Steacher logo
- "Open Camera" button (auto-triggers on load for mobile devices)
- Desktop adaptation: Changes to "Upload Photo" with file picker

**Cropping State (Cropper.js integration):**
- Full-screen image cropper with touch-optimized controls
- Blue crop box outline (4px thick) with white overlay outside crop area
- Responsive cropper with no zoom (prevents confusion)
- Actions: "Retake" or "Send!"
- Loading state with spinner during upload

**Success State:**
- Green checkmark confirmation
- "Take Another Photo" button (if chain_position < 2)
- "Close" button to exit
- Vibration feedback on successful upload (mobile)

**Key Features:**
- No external dependencies except Cropper.js (loaded from CDN)
- Vanilla JavaScript (no Vue on mobile page)
- Image compressed to max 2048x2048 at 85% JPEG quality
- Auto-continuation for chained uploads (next_token)
- Mobile device detection adapts button text and behavior

#### 2. Data Structures (`open_question.ts`)

**PendingImage Interface:**
- Stores upload token (maps to TraceImage.upload_token)
- Stores image URL for preview display

**State Management:**
- `pendingImages` array tracks images awaiting submission
- Starts empty on page load
- Images added after successful QR upload
- Cleared after successful submission
- Individual removal via `removePendingImage(index)` method
- **Token chaining behavior:**
  - After first image upload, modal closes but polling continues silently
  - Desktop polls for subsequent images in the chain using next_token
  - All chained images added to pendingImages automatically
  - Polling stops when submitting answer or closing modal manually

#### 3. UI Components (`open_question.html`)

**Upload Button:**
- Only visible when under 3-image limit
- Text changes: "Upload a picture" → "Upload another picture"
- Disabled during AI processing

**Image Preview:**
- Vertical stack of all pending images
- Each image has individual remove button (X)
- Max height 200px per image

**Submit Button:**
- Enabled with images OR text (not both required)

### Backend Components

#### 1. Token Generation and Chaining (`views_image_upload.py`)

**generate_upload_url() Helper:**
- Extracted reusable function for creating upload tokens
- Creates TraceImage placeholder with 10-minute expiry
- Returns token and expiry timestamp
- Used both for initial generation and chain continuation

**Token Chaining Logic in mobile_upload_submit():**
- Determines chain_position by looking for parent TraceImage with matching next_token
- Generates next_token only if chain_position < 2 (3 photos max)
- Returns next_token in JSON response for mobile to continue
- Updates chain_position field automatically

#### 2. Payload Structure (`open_question.ts` → `views_students.py`)

**Submission includes:**
- Action type (submit_answer, ask_hint, etc.)
- Text answer
- Array of image tokens (may include chained tokens)

#### 3. Image Processing (`logic.py` - `fetch_ai_guidance()`)

**Loading Images for LLM:**
- Fetches TraceImage objects by token
- Converts binary data to Gemini Part objects
- Appends to user message for LLM
- Keeps references for later trace linking
- Handles all images in chain regardless of position

**Linking to Trace:**
- After trace creation, links all images to the trace
- Updates TraceImage.trace foreign key
- Single save per image with update_fields optimization
- Logs count of linked images
- Works transparently with chained images

#### 4. History Serialization (`views_students.py` - exercise detail view)

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
   - **Returns:** `{'status': 'success', 'next_token': <token>}` if more photos allowed
   - **Returns:** `{'status': 'success', 'next_token': null}` if chain limit reached (3 photos)
   - Automatically determines chain_position from parent relationship

4. **Check Status:** `GET /exercises/image/image-status/{token}/`
   - Authenticated endpoint
   - Returns `{'status': 'pending'}` if image not yet uploaded
   - Returns `{'status': 'completed', 'next_token': <token>}` if uploaded and more photos allowed
   - Returns `{'status': 'completed'}` if uploaded and chain complete
   - Returns `{'status': 'expired'}` if token expired
   - Used for polling from desktop to detect both completion and chain continuation

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
- **Improved decorator** (2025-11-16): Simplified rate_limit function with clearer parameters
- Uses Django cache backend for tracking

### File Validation and Processing
- **Input:** Max 30MB, must be image MIME type (enforced by nginx and application)
- **Output:** Resized to max 2048x800 with aspect ratio preservation, optimized
- **Supports:** JPEG, PNG, HEIF, WebP, GIF
- **Transparency:** Preserved for PNG; converted to white background for formats without alpha
- **Processing:** resize_and_convert_image() function handles:
  - Image orientation from EXIF data
  - Aspect ratio calculation and scaling
  - Format conversion to JPEG/PNG
  - Quality optimization (85% JPEG, optimize flag for PNG)
  - Returns binary data, content type, and file size

### nginx Configuration
- **General uploads:** Limited to 2MB (client_max_body_size)
- **Image upload endpoint:** Special location block with 30MB limit
- **Path:** `/exercises/upload/` location gets higher limit to accommodate smartphone photos
- **Rationale:** Balance between security (small default) and usability (large enough for modern photos)
