# Image Upload for Handwritten Answers

## Overview

Allow students to photograph their handwritten responses on paper and upload them for AI evaluation. The system uses a QR code workflow to bridge desktop and mobile devices.

## User Flow

1. **Desktop:** Student is working on an open question exercise on their computer
2. **Desktop:** Student clicks "Upload Answer" button
3. **Desktop:** A QR code appears on screen
4. **Mobile:** Student scans QR code with their phone
5. **Mobile:** Browser opens to a simple upload page (no login required, authenticated via unique URL)
6. **Mobile:** Student takes a photo or selects from gallery
7. **Mobile:** **Student crops the image to focus on the relevant answer area**
8. **Mobile:** Student uploads the image
9. **Mobile:** Success message: "Photo successfully sent"
10. **Desktop:** Page automatically detects the upload (polling or WebSocket)
11. **Desktop:** Uploaded image appears as a preview
12. **Desktop:** Student submits answer (image + optional text)
13. **Backend:** LLM receives both text and image for evaluation

## Current System Analysis

### Relevant Components

- **Frontend:** Vue 3 TypeScript (`frontend/open_question.ts`) with textarea for text answers
- **Backend:** Django views process submissions via `get_guidance()` endpoint in `exercises/views_students.py`
- **LLM Integration:** Gemini API (gemini-2.5-flash) with vision capabilities already configured
- **Data Flow:** Answer → JSON POST → `fetch_ai_guidance()` → Gemini API → Response
- **Models:**
  - `Attempt`: Tracks user attempts at exercises
  - `Trace`: Stores interaction history
  - `ExerciseAsset`: Stores course-level binary files

### Missing Components

- No QR code generation library
- No model for storing attempt-specific images
- No unauthenticated upload endpoint with token-based security
- No image handling in the LLM prompt construction
- No image cropping interface

## Implementation Plan

### Phase 1: Database & Dependencies

#### 1.1 Add Python Dependencies

Add to `requirements.txt`:
```
qrcode[pil]>=7.4.2
# OR
segno>=1.6.0  # Alternative: pure Python, no PIL dependency
```

#### 1.2 Create AttemptImage Model

```python
class AttemptImage(models.Model):
    """
    Image uploaded for an attempt, typically a photo of handwritten work.
    """
    attempt = models.ForeignKey(
        Attempt, 
        on_delete=models.CASCADE, 
        related_name='images'
    )
    image = models.BinaryField(help_text="Store image as binary data")
    upload_token = models.CharField(
        max_length=64, 
        unique=True, 
        db_index=True,
        help_text="Unique token for unauthenticated upload"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    image_type = models.CharField(
        max_length=50, 
        default='image/jpeg',
        help_text="MIME type of the image"
    )
    token_expires_at = models.DateTimeField(
        help_text="When the upload token expires"
    )
    file_size = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Size in bytes"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['attempt', '-created_at']),
            models.Index(fields=['upload_token']),
        ]
```

#### 1.3 Create Migration

```bash
python manage.py makemigrations
python manage.py migrate
```

### Phase 2: Backend - Upload Flow

#### 2.1 Generate Upload Token View (Authenticated)

**Endpoint:** `POST /exercises/<exercise_id>/attempts/<attempt_id>/generate_upload_token/`

**Logic:**
- Validates user owns the attempt
- Generates unique token using `secrets.token_urlsafe(32)`
- Creates `AttemptImage` record with token and expiry (30 minutes)
- Returns JSON with token and full upload URL
- Optionally includes QR code as base64 data URI

**Response:**
```json
{
    "token": "abc123...",
    "upload_url": "https://steacher.example.com/upload/abc123...",
    "expires_at": "2025-10-04T15:30:00Z",
    "qr_code_data_uri": "data:image/png;base64,..."
}
```

#### 2.2 Mobile Upload View (Unauthenticated)

**Endpoint:** `GET /upload/<token>/`

**Logic:**
- Validates token exists and hasn't expired
- Renders mobile-friendly template with camera interface
- Shows exercise title and question (for context)

**Template:** `templates/exercises/mobile_upload.html`
- Mobile-responsive using Bulma
- Large "Take Photo" button
- `<input type="file" accept="image/*" capture="environment">`
- **Image cropping interface** (see Phase 6)
- Preview before upload
- Simple upload button

**Endpoint:** `POST /upload/<token>/`

**Logic:**
- Validates token, checks expiry, checks if already used
- Validates image: file type (JPEG, PNG, WebP), size limit (5MB)
- Stores image in `AttemptImage.image` field
- Marks token as used (optional: single-use tokens)
- Returns success page or JSON response

#### 2.3 Image Retrieval Endpoint (Authenticated)

**Endpoint:** `GET /exercises/<exercise_id>/attempts/<attempt_id>/images/<image_id>/`

**Logic:**
- Validates user owns the attempt
- Serves the image with appropriate content-type header
- Returns 404 if not found or unauthorized

#### 2.4 Image Status/List Endpoint (Authenticated)

**Endpoint:** `GET /exercises/<exercise_id>/attempts/<attempt_id>/images/`

**Logic:**
- Returns list of uploaded images for the attempt
- Used for polling from desktop to detect new uploads

**Response:**
```json
{
    "images": [
        {
            "id": 123,
            "uploaded_at": "2025-10-04T15:25:00Z",
            "file_size": 245678,
            "thumbnail_url": "/exercises/42/attempts/101/images/123/"
        }
    ]
}
```

#### 2.5 Image Delete Endpoint (Authenticated)

**Endpoint:** `DELETE /exercises/<exercise_id>/attempts/<attempt_id>/images/<image_id>/`

**Logic:**
- Validates user owns the attempt
- Deletes the image record
- Returns success response

### Phase 3: Frontend - Desktop UI

#### 3.1 Update `open_question.html`

Add to the exercise controls section:
```html
<div class="control">
    <button
        @click="showUploadDialog"
        class="button is-link"
        :disabled="loadingState !== 'idle'">
        <span class="icon"><i class="fas fa-camera"></i></span>
        <span>Upload Image</span>
    </button>
</div>
```

Add modal for QR code:
```html
<div class="modal" :class="{ 'is-active': showQRModal }">
    <div class="modal-background" @click="closeQRModal"></div>
    <div class="modal-content">
        <div class="box has-text-centered">
            <h3 class="title is-4">Scan to Upload Photo</h3>
            <p class="mb-4">Scan this QR code with your phone to upload a photo of your answer</p>
            <div v-if="qrCodeDataUri">
                <img :src="qrCodeDataUri" alt="QR Code" style="max-width: 300px;">
            </div>
            <p class="mt-4 has-text-grey">
                <span class="icon"><i class="fas fa-clock"></i></span>
                Token expires in [[ timeRemaining ]]
            </p>
            <div v-if="uploadedImages.length > 0" class="mt-4">
                <p class="has-text-success">
                    <span class="icon"><i class="fas fa-check"></i></span>
                    Image uploaded successfully!
                </p>
            </div>
        </div>
    </div>
    <button class="modal-close is-large" @click="closeQRModal"></button>
</div>
```

Add image preview section:
```html
<div v-if="uploadedImages.length > 0" class="box mt-4">
    <h4 class="title is-5">Uploaded Images</h4>
    <div class="columns is-multiline">
        <div v-for="image in uploadedImages" :key="image.id" class="column is-one-third">
            <figure class="image is-square">
                <img :src="image.thumbnail_url" @click="enlargeImage(image)">
            </figure>
            <button @click="deleteImage(image.id)" class="button is-small is-danger is-outlined mt-2">
                <span class="icon"><i class="fas fa-trash"></i></span>
            </button>
        </div>
    </div>
</div>
```

#### 3.2 Update `open_question.ts`

Add to data interface:
```typescript
interface OpenQuestionDataContext {
    // ... existing fields
    showQRModal: boolean;
    qrCodeDataUri: string | null;
    uploadToken: string | null;
    uploadedImages: Array<{id: number, thumbnail_url: string, uploaded_at: string}>;
    pollInterval: number | null;
    tokenExpiresAt: string | null;
}
```

Add methods:
```typescript
async showUploadDialog() {
    // Request upload token from backend
    const response = await csrfFetch(
        `/exercises/${this.exercise.id}/attempts/${attemptId}/generate_upload_token/`,
        { method: 'POST' }
    );
    const data = await response.json();
    
    this.uploadToken = data.token;
    this.qrCodeDataUri = data.qr_code_data_uri;
    this.tokenExpiresAt = data.expires_at;
    this.showQRModal = true;
    
    // Start polling for image uploads
    this.startPolling();
},

async startPolling() {
    this.pollInterval = setInterval(async () => {
        await this.checkForNewImages();
    }, 3000); // Poll every 3 seconds
},

async checkForNewImages() {
    const response = await csrfFetch(
        `/exercises/${this.exercise.id}/attempts/${attemptId}/images/`
    );
    const data = await response.json();
    this.uploadedImages = data.images;
    
    // Stop polling if images uploaded
    if (this.uploadedImages.length > 0 && this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
    }
},

closeQRModal() {
    this.showQRModal = false;
    if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
    }
},

async deleteImage(imageId: number) {
    await csrfFetch(
        `/exercises/${this.exercise.id}/attempts/${attemptId}/images/${imageId}/`,
        { method: 'DELETE' }
    );
    await this.checkForNewImages();
}
```

Modify `submitAnswer()` to include images:
```typescript
submitAnswer() {
    // ... existing code
    const payload = {
        action: 'submit_answer',
        answer: this.userAnswer,
        image_ids: this.uploadedImages.map(img => img.id),
        // ... other fields
    };
}
```

#### 3.3 Add QR Code Library

Add to `open_question.html` import map:
```html
<script type="importmap">
{
  "imports": {
    "qrcode": "https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js",
    ...
  }
}
</script>
```

Or generate QR code on backend and return as base64 data URI (simpler approach).

### Phase 4: Mobile Upload Page

#### 4.1 Create Template `mobile_upload.html`

```html
{% extends "exercises/base.html" %}

{% block content %}
<div id="mobile-upload-app" class="container mt-5" v-cloak>
    <div class="box">
        <h1 class="title is-3">Upload Your Answer</h1>
        <p class="subtitle is-5">{{ exercise_title }}</p>
        
        <div v-if="!imageSelected" class="content">
            <label class="button is-large is-primary is-fullwidth" for="photo-input">
                <span class="icon is-large"><i class="fas fa-camera fa-2x"></i></span>
                <span class="ml-3">Take Photo or Choose File</span>
            </label>
            <input 
                type="file" 
                id="photo-input" 
                accept="image/*" 
                capture="environment"
                style="display: none;"
                @change="handleFileSelect">
        </div>
        
        <div v-if="imageSelected && !uploaded">
            <figure class="image">
                <img :src="imagePreview" alt="Preview">
            </figure>
            
            <!-- Image cropping interface (Phase 6) -->
            <div id="cropper-container" class="my-4"></div>
            
            <div class="buttons mt-4">
                <button @click="uploadImage" class="button is-primary is-large is-fullwidth" :class="{ 'is-loading': uploading }">
                    <span class="icon"><i class="fas fa-upload"></i></span>
                    <span>Upload</span>
                </button>
                <button @click="resetSelection" class="button is-light is-fullwidth">
                    <span class="icon"><i class="fas fa-redo"></i></span>
                    <span>Retake</span>
                </button>
            </div>
        </div>
        
        <div v-if="uploaded" class="notification is-success is-light">
            <span class="icon is-large"><i class="fas fa-check-circle fa-3x"></i></span>
            <h2 class="title is-4 mt-3">Photo Successfully Sent!</h2>
            <p>You can now return to your computer.</p>
        </div>
        
        <div v-if="error" class="notification is-danger">
            <p>[[ error ]]</p>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script type="module">
import { createApp } from 'vue';

const app = createApp({
    delimiters: ['[[', ']]'],
    data() {
        return {
            imageSelected: false,
            imagePreview: null,
            selectedFile: null,
            croppedBlob: null,
            uploading: false,
            uploaded: false,
            error: null,
            token: '{{ token }}',
        };
    },
    methods: {
        handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;
            
            // Validate file type
            if (!file.type.startsWith('image/')) {
                this.error = 'Please select an image file';
                return;
            }
            
            // Validate file size (5MB)
            if (file.size > 5 * 1024 * 1024) {
                this.error = 'Image is too large. Maximum size is 5MB';
                return;
            }
            
            this.selectedFile = file;
            this.imagePreview = URL.createObjectURL(file);
            this.imageSelected = true;
            this.error = null;
            
            // Initialize cropper (Phase 6)
            this.$nextTick(() => {
                this.initCropper();
            });
        },
        
        initCropper() {
            // To be implemented in Phase 6
            // Will use a library like Cropper.js
        },
        
        async uploadImage() {
            this.uploading = true;
            this.error = null;
            
            try {
                const formData = new FormData();
                
                // Use cropped image if available, otherwise original
                const fileToUpload = this.croppedBlob || this.selectedFile;
                formData.append('image', fileToUpload);
                
                const response = await fetch(`/upload/${this.token}/`, {
                    method: 'POST',
                    body: formData,
                });
                
                if (!response.ok) {
                    throw new Error('Upload failed');
                }
                
                this.uploaded = true;
            } catch (error) {
                this.error = 'Upload failed. Please try again.';
            } finally {
                this.uploading = false;
            }
        },
        
        resetSelection() {
            this.imageSelected = false;
            this.imagePreview = null;
            this.selectedFile = null;
            this.croppedBlob = null;
            this.error = null;
            document.getElementById('photo-input').value = '';
        }
    }
});

app.mount('#mobile-upload-app');
</script>
{% endblock %}
```

#### 4.2 Views for Mobile Upload

In `exercises/views_students.py`:

```python
@require_GET
def mobile_upload_page(request, token):
    """
    Render the mobile upload page (no authentication required).
    """
    try:
        image = get_object_or_404(AttemptImage, upload_token=token)
        
        # Check if token has expired
        if timezone.now() > image.token_expires_at:
            return render(request, 'exercises/upload_expired.html', status=403)
        
        # Check if already uploaded
        if image.image:
            return render(request, 'exercises/upload_already_used.html', status=400)
        
        attempt = image.attempt
        exercise = attempt.exercise
        
        return render(request, 'exercises/mobile_upload.html', {
            'token': token,
            'exercise_title': exercise.title,
            'exercise_question': exercise.question[:200],  # First 200 chars for context
        })
    except Exception as e:
        logger.exception("Error in mobile_upload_page")
        return HttpResponse("Invalid or expired upload link", status=400)


@require_POST
@csrf_exempt  # Token provides security
def mobile_upload_submit(request, token):
    """
    Handle the image upload from mobile (no authentication required).
    """
    try:
        image_record = get_object_or_404(AttemptImage, upload_token=token)
        
        # Validate token not expired
        if timezone.now() > image_record.token_expires_at:
            return JsonResponse({'error': 'Token expired'}, status=403)
        
        # Validate not already used
        if image_record.image:
            return JsonResponse({'error': 'Token already used'}, status=400)
        
        # Get uploaded file
        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return JsonResponse({'error': 'No image provided'}, status=400)
        
        # Validate file type
        if not uploaded_file.content_type.startswith('image/'):
            return JsonResponse({'error': 'Invalid file type'}, status=400)
        
        # Validate file size (5MB)
        if uploaded_file.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'File too large (max 5MB)'}, status=400)
        
        # Store the image
        image_record.image = uploaded_file.read()
        image_record.image_type = uploaded_file.content_type
        image_record.file_size = uploaded_file.size
        image_record.save()
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        logger.exception("Error in mobile_upload_submit")
        return JsonResponse({'error': 'Upload failed'}, status=500)
```

### Phase 5: LLM Integration

#### 5.1 Modify `fetch_ai_guidance()` in `logic.py`

Update function signature and logic:

```python
def fetch_ai_guidance(data: dict, exercise: Exercise, attempt: Attempt) -> dict:
    """
    Fetches AI guidance for a given exercise and attempt.
    Now supports image uploads.
    
    Input data keys:
        - 'image_ids': list of AttemptImage IDs (optional)
        - ... other existing keys
    """
    
    # ... existing code ...
    
    # Build user message content (can now be multimodal)
    user_message_parts = []
    
    # Text content
    user_prompt_content = ""
    # ... construct text as before ...
    if user_prompt_content:
        user_message_parts.append(Part(text=user_prompt_content))
    
    # Image content
    image_ids = data.get('image_ids', [])
    if image_ids:
        images = AttemptImage.objects.filter(id__in=image_ids, attempt=attempt)
        for img in images:
            if img.image:
                import base64
                image_b64 = base64.b64encode(bytes(img.image)).decode('utf-8')
                user_message_parts.append(
                    Part(inline_data={
                        'mime_type': img.image_type,
                        'data': image_b64
                    })
                )
    
    # ... existing code to build history ...
    
    # Send message with both text and images
    gen_response = chat_session.send_message(user_message_parts)
    
    # ... rest of existing code ...
```

#### 5.2 Update System Prompt for Handwriting

In `templates/exercises/prompts/exercise_guidance.md` or course-specific prompts, add:

```markdown
## Handwritten Answers

If the student provides an image of their handwritten answer:
1. First, extract and transcribe the handwritten text as accurately as possible
2. Evaluate the answer based on the transcribed content
3. If the handwriting is unclear, ask for clarification or request they type it out
4. Be patient and helpful with handwriting recognition limitations
```

### Phase 6: Image Cropping Interface

**Requirement:** Students need to crop their photo to focus only on the relevant answer area, removing extraneous parts of the page or background.

#### 6.1 Add Cropping Library

Add to mobile upload template:

```html
<!-- Cropper.js for image cropping -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.js"></script>
```

Or use a lightweight alternative like:
- `react-easy-crop` (if adding React)
- `vue-advanced-cropper` (Vue-specific)
- Custom canvas-based cropper (lightweight, no dependencies)

#### 6.2 Implement Cropping UI

Update `initCropper()` method in mobile upload:

```typescript
initCropper() {
    const image = document.querySelector('#cropper-container img');
    
    this.cropper = new Cropper(image, {
        aspectRatio: NaN, // Free aspect ratio
        viewMode: 1,
        autoCropArea: 0.8,
        responsive: true,
        guides: true,
        center: true,
        highlight: true,
        cropBoxResizable: true,
        cropBoxMovable: true,
        toggleDragModeOnDblclick: false,
    });
}
```

Update `uploadImage()` to use cropped image:

```typescript
async uploadImage() {
    this.uploading = true;
    this.error = null;
    
    try {
        // Get cropped canvas
        const canvas = this.cropper.getCroppedCanvas({
            maxWidth: 2048,  // Limit size
            maxHeight: 2048,
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'high',
        });
        
        // Convert to blob
        this.croppedBlob = await new Promise((resolve) => {
            canvas.toBlob(resolve, 'image/jpeg', 0.85);
        });
        
        const formData = new FormData();
        formData.append('image', this.croppedBlob, 'answer.jpg');
        
        // ... rest of upload logic
    } catch (error) {
        this.error = 'Failed to process image. Please try again.';
    } finally {
        this.uploading = false;
    }
}
```

#### 6.3 Cropping UI/UX

- Show crop handles clearly on mobile (large touch targets)
- Add zoom in/out buttons for fine-tuning
- Add rotate button if needed
- Show instructions: "Drag to select the area containing your answer"
- Preview the cropped area before upload
- Option to skip cropping (use original image)

### Phase 7: URL Routing

Add to `exercises/urls.py`:

```python
# Image upload endpoints
path('<int:exercise_id>/attempts/<int:attempt_id>/generate_upload_token/', 
     views_students.generate_upload_token, name='generate_upload_token'),
path('<int:exercise_id>/attempts/<int:attempt_id>/images/', 
     views_students.list_attempt_images, name='list_attempt_images'),
path('<int:exercise_id>/attempts/<int:attempt_id>/images/<int:image_id>/', 
     views_students.serve_attempt_image, name='serve_attempt_image'),

# Mobile upload (unauthenticated)
path('upload/<str:token>/', views_students.mobile_upload_page, name='mobile_upload_page'),
```

Note: The POST to the same URL pattern is handled by checking request method in the view.

## Security Considerations

1. **Token Security:**
   - Use cryptographically secure random tokens (`secrets.token_urlsafe(32)`)
   - 30-minute expiry time
   - Consider single-use tokens (can't upload multiple times)
   - Store hashed version in DB (optional, adds complexity)

2. **Rate Limiting:**
   - Max 3-5 images per attempt
   - Max file size: 5MB per image
   - Rate limit token generation (prevent spam)

3. **File Validation:**
   - Check MIME type (image/jpeg, image/png, image/webp)
   - Validate actual file content (not just extension)
   - Sanitize filenames
   - Scan for malware (optional, may be overkill)

4. **CSRF Protection:**
   - Upload endpoint can skip CSRF (token provides security)
   - Mark view with `@csrf_exempt`

5. **Authorization:**
   - Token-based uploads don't require authentication
   - Viewing/deleting images requires user to own the attempt
   - No direct image URLs without authentication

## Technical Decisions & Alternatives

### QR Code Library Choice

**Option A: Backend generation (Recommended)**
- Use `qrcode` or `segno` library in Python
- Generate QR code in view, return as base64 data URI
- Simpler frontend, no extra JS dependency
- **Chosen approach**

**Option B: Frontend generation**
- Use `qrcode.js` or similar
- Generate QR code in browser
- Saves a round-trip, but adds JS dependency

### Image Storage

**Option A: BinaryField (Recommended)**
- Store in database as `BinaryField`
- Consistent with existing `ExerciseAsset` pattern
- Simple, no external dependencies
- Good for small-medium images
- **Chosen approach**

**Option B: FileField with storage backend**
- Use Django `FileField` with filesystem or S3
- Better for large images or high volume
- More complex setup

### Token Management

**Option A: Expiring tokens in DB (Recommended)**
- Store token with expiry timestamp
- Simple, works without Redis
- **Chosen approach**

**Option B: Signed URLs**
- Use Django's `signing` module
- Stateless, no DB record needed
- Can't revoke or track usage

### Real-time Updates

**Option A: Polling (Recommended)**
- Frontend polls every 2-3 seconds for new images
- Simple to implement
- Works with existing setup
- **Chosen approach**

**Option B: WebSockets**
- Use Django Channels (already configured)
- Real-time updates, no polling
- More complex, requires WebSocket handling

## Open Questions

1. **Image limits:** How many images per attempt? (Suggest: 1-3)

2. **Image persistence:** Keep indefinitely or delete after completion?

3. **Token expiry:** 30 minutes sufficient? Make configurable?

4. **Text + Image:** Should images supplement or replace text answers?

5. **Teacher view:** Show images in analytics/grading views?

6. **Image quality:** Implement client-side compression? Balance between quality and LLM cost

7. **Multiple submissions:** Can students upload multiple times with same QR code?

8. **Fallback:** What if LLM can't read handwriting? Show error and ask to type instead?

9. **Image orientation:** Auto-rotate images based on EXIF data?

10. **Cropping UI:** Mandatory or optional? Skip button for quick uploads?

## Future Enhancements

- Batch upload multiple images at once
- OCR preprocessing before LLM (extract text, save cost)
- Image enhancement (auto-contrast, despeckle)
- Support for diagrams, sketches, math notation
- Teacher annotation tools on images
- Download all attempt images as ZIP
- Mobile app instead of web upload
- Handwriting-to-text API integration (Google Cloud Vision, Azure)

## Testing Checklist

- [ ] Token generation and expiry
- [ ] QR code display and scanning
- [ ] Mobile upload with camera
- [ ] Mobile upload with file picker
- [ ] Image cropping interface on mobile
- [ ] File type validation
- [ ] File size validation
- [ ] Token reuse prevention
- [ ] Desktop polling for new images
- [ ] Image preview on desktop
- [ ] Image deletion
- [ ] Answer submission with images
- [ ] LLM receiving both text and images
- [ ] Handwriting evaluation accuracy
- [ ] Error handling (expired token, upload failure)
- [ ] Mobile responsive design
- [ ] Cross-browser compatibility (iOS Safari, Chrome, Firefox)
- [ ] Slow network conditions
- [ ] Multiple concurrent uploads

## Cost Considerations

**LLM Vision API Costs:**
- Gemini Flash: ~$0.0001875 per image (input)
- Images count toward token limit
- Consider image resolution limits to control cost
- Monitor usage and implement limits per student

**Storage:**
- Database storage for images (PostgreSQL)
- Estimate: 1-2MB per image
- 1000 students × 10 exercises × 2 images = ~20GB
- Consider periodic cleanup of old images

## Implementation Priority

1. **MVP (Minimum Viable Product):**
   - Token generation
   - Mobile upload page (no cropping)
   - Desktop polling and preview
   - LLM integration with images

2. **Phase 2:**
   - QR code generation
   - Image cropping interface
   - UI polish

3. **Phase 3:**
   - Analytics/teacher view
   - Advanced features (batch upload, OCR, etc.)

## References

- Gemini Vision API: https://ai.google.dev/gemini-api/docs/vision
- QRCode library: https://github.com/lincolnloop/python-qrcode
- Cropper.js: https://github.com/fengyuanchen/cropperjs
- Django file uploads: https://docs.djangoproject.com/en/5.0/topics/http/file-uploads/

