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
        };
    },
    mounted() {
        console.log('[MobileChat] Component mounted');
        this.scrollToBottom();
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
        updateSendButton() {
            // Logic handled by reactive binding in template
            this.autoResizeTextarea();
        },
        
        autoResizeTextarea() {
            this.$nextTick(() => {
                const textarea = this.$refs.messageInput as HTMLTextAreaElement;
                if (!textarea) return;
                
                // Reset height to auto to get the correct scrollHeight
                textarea.style.height = 'auto';
                
                // Set height based on scrollHeight, respecting max-height from CSS
                const newHeight = Math.min(textarea.scrollHeight, 120);
                textarea.style.height = newHeight + 'px';
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
                
                this.mediaRecorder = new MediaRecorder(stream, { mimeType });
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
                
            } catch (error) {
                console.error('Error accessing microphone:', error);
                this.audioStream = null;
                alert('Could not access microphone. Please check permissions.');
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
