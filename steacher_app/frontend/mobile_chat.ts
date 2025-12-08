// Mobile chat interface for Steacher exercises

import { defineComponent } from 'vue';
import { csrfFetch } from './utils';
import confetti from 'canvas-confetti';
import { renderMarkdown } from './markdown_utils';

interface LocalImage {
    type: 'local';
    blob: Blob;
    url: string;
    id: string;
}

interface RemoteImage {
    type: 'remote';
    url: string;
}

type ImageAttachment = LocalImage | RemoteImage;

interface Message {
    role: 'user' | 'assistant';
    content: string;
    images?: ImageAttachment[];
}

const MobileChatComponent = defineComponent({
    props: {
        exerciseId: {
            type: Number,
            required: true,
        },
        attemptId: {
            type: Number,
            required: true,
        },
        initialMessages: {
            type: Array as () => Message[],
            default: () => [],
        },
        transcribeUrl: {
            type: String,
            required: true,
        },
        exerciseQuestion: {
            type: String,
            default: '',
        }
    },
    computed: {
        renderedQuestion(): string {
            return renderMarkdown(this.exerciseQuestion, true);
        },
        messagesContainerStyle(): { paddingBottom: string } {
            return { paddingBottom: `${this.inputContainerHeight + 16}px` };
        }
    },
    data() {
        // Clean initial messages of any special tags and mark images as remote
        const cleanedMessages = this.initialMessages.map(msg => {
            const cleaned = { ...msg };
            
            if (msg.role === 'assistant' && msg.content) {
                cleaned.content = msg.content.replace('<exercise_completed>', '')
                                           .replace('<solution_revealed>', '')
                                           .trim();
            }
            
            // Ensure images have the 'type' field
            if (cleaned.images && Array.isArray(cleaned.images)) {
                cleaned.images = cleaned.images.map((img: any) => {
                    if ('type' in img) {
                        return img as ImageAttachment;
                    }
                    // Mark existing images as remote
                    return {
                        type: 'remote' as const,
                        url: (img.url || '') as string
                    } as RemoteImage;
                });
            }
            
            return cleaned;
        });

        return {
            messages: cleanedMessages as Message[],
            messageText: '',
            pendingImages: [] as LocalImage[],
            isLoading: false,
            isRecording: false,
            isTranscribing: false,
            mediaRecorder: null as MediaRecorder | null,
            audioStream: null as MediaStream | null,
            audioChunks: [] as Blob[],
            cropper: null as any,
            showCropper: false,
            cropperImageSrc: '',
            fullScreenImage: null as string | null,
            isZoomed: false,
            textareaHeight: 36,
            inputContainerHeight: 100,
            microphoneAvailable: true,
            microphoneError: null as string | null,
        };
    },
    watch: {
        messageText() {
            this.autoResizeTextarea();
        },
        textareaHeight() {
            this.updateInputContainerHeight();
        },
        pendingImages() {
            this.updateInputContainerHeight();
        },
        isRecording() {
            this.updateInputContainerHeight();
        },
        isTranscribing() {
            this.updateInputContainerHeight();
        },
    },
    mounted() {
        console.log('[MobileChat] Component mounted');
        this.updateInputContainerHeight();
        this.scrollToBottom();
        this.checkMicrophoneAvailability();
    },
    unmounted() {
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }
        if (this.cropper) {
            this.cropper.destroy();
        }
    },
    methods: {
        async checkMicrophoneAvailability() {
            const diagnostics: string[] = [];
            
            // Check basic support
            diagnostics.push(`getUserMedia available: ${!!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)}`);
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                this.microphoneAvailable = false;
                this.microphoneError = 'Browser does not support audio recording';
                console.warn('[MobileChat] getUserMedia not supported');
                console.log('[MobileChat] Diagnostics:\n' + diagnostics.join('\n'));
                return;
            }
            
            // Check secure context
            diagnostics.push(`Secure context (HTTPS): ${window.isSecureContext}`);
            diagnostics.push(`Protocol: ${window.location.protocol}`);
            diagnostics.push(`User agent: ${navigator.userAgent}`);
            
            if (!window.isSecureContext) {
                this.microphoneAvailable = false;
                this.microphoneError = 'HTTPS required for microphone access';
                console.warn('[MobileChat] Not in secure context (HTTPS required for microphone)');
                console.log('[MobileChat] Diagnostics:\n' + diagnostics.join('\n'));
                return;
            }
            
            // Check for audio input devices
            try {
                if (navigator.mediaDevices.enumerateDevices) {
                    const devices = await navigator.mediaDevices.enumerateDevices();
                    const audioInputs = devices.filter(device => device.kind === 'audioinput');
                    diagnostics.push(`Audio input devices found: ${audioInputs.length}`);
                    
                    if (audioInputs.length === 0) {
                        this.microphoneAvailable = false;
                        this.microphoneError = 'No microphone found on device';
                        console.warn('[MobileChat] No audio input devices found');
                        console.log('[MobileChat] Diagnostics:\n' + diagnostics.join('\n'));
                        return;
                    }
                } else {
                    diagnostics.push('enumerateDevices: not available');
                }
            } catch (error) {
                diagnostics.push('enumerateDevices: query failed');
                console.log('[MobileChat] enumerateDevices failed:', error);
            }
            
            // Check permission status (if Permissions API is available)
            try {
                if (navigator.permissions && navigator.permissions.query) {
                    const result = await navigator.permissions.query({ name: 'microphone' as PermissionName });
                    diagnostics.push(`Permission status: ${result.state}`);
                    console.log('[MobileChat] Microphone permission status:', result.state);
                    
                    if (result.state === 'denied') {
                        this.microphoneAvailable = false;
                        this.microphoneError = 'Microphone permission denied';
                        console.warn('[MobileChat] Microphone permission denied');
                    } else if (result.state === 'granted') {
                        this.microphoneAvailable = true;
                        this.microphoneError = null;
                    }
                } else {
                    diagnostics.push('Permission API: not available');
                }
            } catch (error) {
                // Permissions API may not be fully supported, that's okay
                diagnostics.push('Permission API: query failed');
                console.log('[MobileChat] Permissions API not available or query failed');
            }
            
            console.log('[MobileChat] Diagnostics:\n' + diagnostics.join('\n'));
        },
        
        autoResizeTextarea() {
            this.$nextTick(() => {
                const textarea = this.$refs.messageInput as HTMLTextAreaElement;
                if (!textarea) return;
                
                // If empty, reset to minimum height
                if (!this.messageText.trim()) {
                    textarea.style.height = '36px';
                    this.textareaHeight = 36;
                    return;
                }
                
                // Reset height to auto to get the correct scrollHeight
                textarea.style.height = 'auto';
                
                // Set height based on scrollHeight, respecting max-height from CSS
                const newHeight = Math.min(textarea.scrollHeight, 120);
                textarea.style.height = newHeight + 'px';
                
                // Update reactive height tracker
                this.textareaHeight = newHeight;
            });
        },
        
        updateInputContainerHeight() {
            this.$nextTick(() => {
                const inputContainer = document.querySelector('.mobile-chat-input-container') as HTMLElement;
                if (!inputContainer) return;
                
                this.inputContainerHeight = inputContainer.offsetHeight;
            });
        },
        
        openCamera() {
            const input = this.$refs.cameraInput as HTMLInputElement;
            if (input) input.click();
        },
        
        async handleCameraCapture(event: Event) {
            const target = event.target as HTMLInputElement;
            const file = target.files?.[0];
            if (!file) return;
            
            // Read file to display in cropper
            const reader = new FileReader();
            reader.onload = (e) => {
                if (e.target?.result) {
                    this.cropperImageSrc = e.target.result as string;
                    this.showCropper = true;
                    // Wait for Vue to render the modal and image, then init cropper
                    this.$nextTick(() => {
                        this.initCropper();
                    });
                }
            };
            reader.readAsDataURL(file);
            target.value = '';
        },
        
        initCropper() {
            if (this.cropper) {
                this.cropper.destroy();
            }
            
            const img = this.$refs.cropperImage as HTMLImageElement;
            if (!img) return;

            // Ensure image is loaded
            if (!img.complete) {
                img.onload = () => this.initCropper();
                return;
            }

            // @ts-ignore - Cropper is loaded from CDN
            this.cropper = new Cropper(img, {
                viewMode: 1,
                dragMode: 'move',
                aspectRatio: NaN,
                autoCropArea: 1.0,
                responsive: true,
                movable: true,
                zoomable: true,
                zoomOnTouch: true,
                scalable: true,
                cropBoxMovable: true,
                cropBoxResizable: true,
                minContainerWidth: 200,
                minContainerHeight: 200,
            });
        },

        confirmCrop() {
            console.log('[MobileChat] confirmCrop called');
            if (!this.cropper) {
                console.error('[MobileChat] Cropper not initialized!');
                return;
            }

            try {
                const canvas = this.cropper.getCroppedCanvas({
                    maxWidth: 2048,
                    maxHeight: 2048,
                    imageSmoothingQuality: 'high',
                });
                
                canvas.toBlob((blob: Blob | null) => {
                    if (blob) {
                        this.addImage(blob);
                    } else {
                        console.error('[MobileChat] Blob is null!');
                    }
                    this.closeCropper();
                }, 'image/jpeg', 0.85);
            } catch (error) {
                console.error('[MobileChat] Error in confirmCrop:', error);
                alert('Failed to crop image. Please try again.');
                this.closeCropper();
            }
        },

        cancelCrop() {
            this.closeCropper();
            this.openCamera();
        },

        closeCropper() {
            if (this.cropper) {
                this.cropper.destroy();
                this.cropper = null;
            }
            this.showCropper = false;
            this.cropperImageSrc = '';
        },
        
        addImage(blob: Blob) {
            console.log('[MobileChat] addImage called, blob size:', blob.size);
            
            if (this.pendingImages.length >= 3) {
                alert('Maximum 3 images allowed');
                return;
            }
            
            const image: LocalImage = {
                type: 'local',
                blob,
                url: URL.createObjectURL(blob),
                id: Math.random().toString(36).substring(7),
            };
            
            this.pendingImages.push(image);
            console.log('[MobileChat] pendingImages count:', this.pendingImages.length);
        },
        
        removeImage(id: string) {
            const index = this.pendingImages.findIndex(img => img.id === id);
            if (index > -1 && this.pendingImages[index]) {
                URL.revokeObjectURL(this.pendingImages[index].url);
                this.pendingImages.splice(index, 1);
            }
        },
        
        toggleRecording() {
            if (this.isRecording) {
                this.stopRecording();
            } else {
                this.startRecording();
            }
        },
        
        async startRecording() {
            if (this.isRecording) return;
            
            try {
                if (!this.audioStream || !this.audioStream.active) {
                    this.audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                }
                
                const stream = this.audioStream;
                if (!stream) {
                    throw new Error('Audio stream is null');
                }
                const mimeType = this.getBestAudioMimeType();
                
                // Only pass mimeType option if we found a supported type. Else, it might cause authorization errors on Android
                this.mediaRecorder = mimeType 
                    ? new MediaRecorder(stream, { mimeType })
                    : new MediaRecorder(stream);
                this.audioChunks = [];
                
                this.mediaRecorder.addEventListener('dataavailable', (event) => {
                    this.audioChunks.push(event.data);
                });
                
                this.mediaRecorder.addEventListener('stop', () => {
                    const audioBlob = new Blob(this.audioChunks, { type: mimeType });
                    this.transcribeAudio(audioBlob);
                });
                
                this.mediaRecorder.start();
                this.isRecording = true;
                
            } catch (error: any) {
                console.error('Error accessing microphone:', error);
                console.error('Error details:', {
                    name: error.name,
                    message: error.message,
                    isSecureContext: window.isSecureContext,
                    protocol: window.location.protocol,
                });
                this.audioStream = null;
                
                // Provide specific error messages based on error type
                let message = 'Could not access microphone. ';
                
                if (error.name === 'NotSupportedError') {
                    message += 'Audio recording format not supported on this device.';
                } else if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                    message += 'Permission denied. Please allow microphone access in your browser settings:\n\n';
                    message += '1. Tap the lock icon or "i" in the address bar\n';
                    message += '2. Find "Microphone" permissions\n';
                    message += '3. Change to "Allow"\n';
                    message += '4. Reload the page';
                } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
                    message += 'No microphone found on your device.';
                } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
                    message += 'Microphone is already in use by another application.';
                } else if (error.name === 'OverconstrainedError') {
                    message += 'Could not start microphone with the requested settings.';
                } else if (error.name === 'SecurityError') {
                    message += 'Security error. Make sure you are using HTTPS.';
                } else {
                    message += `Error: ${error.name} - ${error.message}`;
                }
                
                alert(message);
            }
        },
        
        stopRecording() {
            if (!this.isRecording || !this.mediaRecorder) return;
            
            this.mediaRecorder.stop();
            this.isRecording = false;
        },
        
        getBestAudioMimeType(): string {
            const types = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/mp4',
                'audio/ogg;codecs=opus',
            ];
            
            for (const type of types) {
                if (MediaRecorder.isTypeSupported(type)) {
                    return type;
                }
            }
            
            return '';
        },
        
        async transcribeAudio(audioBlob: Blob) {
            try {
                const formData = new FormData();
                formData.append('audio', audioBlob, 'recording.webm');
                
                this.isTranscribing = true;
                
                const response = await csrfFetch(this.transcribeUrl, {
                    method: 'POST',
                    body: formData,
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    this.messageText = data.text;
                    this.autoResizeTextarea();
                } else {
                    this.showError('Transcription failed: ' + (data.message || 'Unknown error'));
                }
                
            } catch (error) {
                console.error('Error transcribing audio:', error);
                this.showError('Failed to transcribe audio. Please try again.');
            } finally {
                this.isTranscribing = false;
            }
        },
        
        async sendMessage() {
            const text = this.messageText.trim();
            if (!text && this.pendingImages.length === 0) return;
            
            // Create message with pending images for optimistic UI
            const optimisticImages: ImageAttachment[] = this.pendingImages.map(img => ({
                type: 'local',
                url: img.url,
                blob: img.blob,
                id: img.id
            }));

            this.messages.push({
                role: 'user',
                content: text,
                images: optimisticImages.length > 0 ? optimisticImages : undefined,
            });
            
            // Prepare for sending
            const imagesToSend = [...this.pendingImages];
            
            // Clear input state
            this.messageText = '';
            this.pendingImages = [];
            this.autoResizeTextarea();
            
            // Show loading
            this.isLoading = true;
            this.scrollToBottom();
            
            try {
                const formData = new FormData();
                const requestData = {
                    action: 'submit_answer',
                    answer: text,
                };
                formData.append('data', JSON.stringify(requestData));
                
                // Only append local blobs
                imagesToSend.forEach((img, index) => {
                    formData.append(`image_${index}`, img.blob, `image_${index}.jpg`);
                });
                
                const url = `/exercises/${this.exerciseId}/attempts/${this.attemptId}/guidance/`;
                const response = await csrfFetch(url, {
                    method: 'POST',
                    body: formData,
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    this.handleAssistantResponse(data.guidance || '');
                } else {
                    this.showError(data.message || 'Failed to get response');
                }
                
            } catch (error) {
                console.error('Error sending message:', error);
                this.showError('Failed to send message. Please try again.');
            } finally {
                this.isLoading = false;
                this.scrollToBottom();
            }
        },
        
        handleAssistantResponse(guidance: string) {
            const isComplete = guidance.includes('<exercise_completed>');
            const isSolutionReveal = guidance.includes('<solution_revealed>');
            
            // Strip tags
            const cleanContent = guidance.replace('<exercise_completed>', '')
                                       .replace('<solution_revealed>', '')
                                       .trim();
            
            if (isComplete && !isSolutionReveal) {
                confetti({ particleCount: 200, spread: 150, origin: { y: 0.6 } });
            }
            
            this.messages.push({
                role: 'assistant',
                content: cleanContent,
            });
        },

        showError(message: string) {
            this.messages.push({
                role: 'assistant',
                content: `⚠️ ${message}`,
            });
            this.scrollToBottom();
        },
        
        scrollToBottom() {
            this.$nextTick(() => {
                const container = this.$refs.messagesContainer as HTMLElement;
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            });
        },
        
        renderMarkdown,

        openFullScreen(url: string) {
            this.fullScreenImage = url;
            this.isZoomed = false;
            document.body.style.overflow = 'hidden';
        },

        closeFullScreen() {
            this.fullScreenImage = null;
            this.isZoomed = false;
            document.body.style.overflow = '';
        },

        toggleZoom(event: Event) {
            event.stopPropagation();
            this.isZoomed = !this.isZoomed;
        },

        handleImageClick(event: MouseEvent) {
            const target = event.target as HTMLElement;
            if (target.tagName === 'IMG' && (target.closest('.mobile-chat-message-bubble') || target.closest('.mobile-chat-image-thumb'))) {
                const img = target as HTMLImageElement;
                this.openFullScreen(img.src);
            }
        },
    },
});

// Export factory function for global access
export default {
    createApp(element: string | HTMLElement, config: { 
        exerciseId: number; 
        attemptId: number; 
        initialMessages: Message[]; 
        transcribeUrl: string;
        exerciseQuestion?: string;
    }) {
        console.log('[MobileChat] createApp called with config:', config);
        const { createApp } = (window as any).Vue;
        const app = createApp(MobileChatComponent, {
            exerciseId: config.exerciseId,
            attemptId: config.attemptId,
            initialMessages: config.initialMessages || [],
            transcribeUrl: config.transcribeUrl,
            exerciseQuestion: config.exerciseQuestion || '',
        });
        
        const instance = app.mount(element);
        return instance;
    },
};
