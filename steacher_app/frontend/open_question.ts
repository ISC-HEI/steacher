import { ChatbotPanel } from './ChatbotPanel.js';
import { createApp, defineComponent } from 'vue';
import confetti from 'canvas-confetti';
import type { Exercise } from './utils.js';
import { csrfFetch, getCsrfToken } from './utils.js';
import { renderMarkdown } from './markdown_utils.js';

interface ImageBeingUploaded {
    /** An image that is being uploaded; will be added to the user's message.  */
    
    /** The upload token of the image. Maps to TraceImage.upload_token */
    image_token: string;
    url: string;
}

interface OpenQuestionDataContext {
    exercise: Exercise;
    userAnswer: string;
    queryError: string | null;
    loadingState: 'idle' | 'getting-guidance';
    start_timestamp: string;
    showQRModal: boolean;
    uploadToken: string | null;
    qrCodeDataUri: string | null;
    isPolling: boolean;
    pendingImages: ImageBeingUploaded[];
    pollingInterval: number | null;
}

document.addEventListener('DOMContentLoaded', function() {
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('openq-exercise-app');

    if (!exerciseDataScript || !appElement) {
        console.error('Required script tags or app element not found!');
        return;
    }
    const exerciseData: Exercise = JSON.parse(exerciseDataScript.textContent || '{}');

    // Get attempt ID from script tag
    const attemptIdScript = document.getElementById('attempt-id');
    let attemptId: number | null = null;
    if (attemptIdScript && attemptIdScript.textContent) {
        attemptId = JSON.parse(attemptIdScript.textContent);
    }

    // Get interactions if they exist
    const interactionsScript = document.getElementById('interactions-data');
    let initialMessages: any[] = [];
    let lastAnswer = '';
    if (interactionsScript) {
        const logs = JSON.parse(interactionsScript.textContent || '[]') as any[];
        // Find last user answer in metadata
        for (let i = logs.length - 1; i >= 0; i--) {
            const log = logs[i];
            const meta = (log.user_submission && log.user_submission.metadata) || {};
            if (meta && typeof meta.answer === 'string') {
                lastAnswer = meta.answer;
                break;
            }
        }
        logs.forEach((log: any) => {
            if (log.user_submission) initialMessages.push(log.user_submission);
            if (log.llm_response) initialMessages.push(log.llm_response);
        });
    }

    const OpenQuestionApp = defineComponent({
        delimiters: ['[[', ']]'],
        data(): OpenQuestionDataContext {
            // Get persistence key for localStorage
            const persistenceKey = `open_question_${exerciseData.id}`;
            let initialAnswer = lastAnswer || (exerciseData.exercise_data && exerciseData.exercise_data.answer_template) || '';

            // Try to restore from localStorage if no previous answer exists
            if (!lastAnswer) {
                try {
                    const savedContent = localStorage.getItem(persistenceKey);
                    if (savedContent && savedContent !== initialAnswer) {
                        initialAnswer = savedContent;
                    }
                } catch (e) {
                    console.warn('Error restoring answer from localStorage', e);
                }
            }

            return {
                exercise: exerciseData,
                userAnswer: initialAnswer,
                queryError: null,
                loadingState: 'idle',
                start_timestamp: new Date().toISOString(),
                showQRModal: false,
                uploadToken: null,
                qrCodeDataUri: null,
                isPolling: false,
                pendingImages: [],
                pollingInterval: null,
            };
        },
        async mounted() {
            // @ts-ignore
            const chatbotPanel = this.$refs.chatbotPanel as any;

            // IMPORTANT: Check for and display pre-existing feedback FIRST.
            // This ensures the trigger guard in displayMessage works correctly.
            const feedbackScript = document.getElementById('completion-feedback-data');
            if (feedbackScript && feedbackScript.textContent) {
                try {
                    const feedbackData = JSON.parse(feedbackScript.textContent);
                    if (feedbackData && chatbotPanel) {
                        chatbotPanel.displayRecommendation(feedbackData);
                    }
                } catch (e) {
                    console.error("Failed to parse completion feedback data", e);
                }
            }

            // Now, display the initial chat messages
            if (chatbotPanel) {
                initialMessages.forEach(msg => chatbotPanel.displayMessage(msg));
            }
            
            // Expose for quiz mode auto-submit
            (window as any).submitAnswer = () => this.submitAnswer();
        },
        methods: {
            renderMarkdown(this: any, content: string) {
                if (!content) return '';
                // Enable math rendering only if exercise allows image upload (indicates math exercise)
                const enableMath = exerciseData.allow_image_upload || false;
                return renderMarkdown(content, enableMath);
            },
            async getGuidance(action: 'submit_answer' | 'ask_hint' | 'ask_question', details: { question?: string | null } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    const csrfToken = getCsrfToken();

                    const payload: any = {
                        action: action,
                        answer: this.userAnswer,
                        question: details.question || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString(),
                        image_tokens: this.pendingImages.map(img => img.image_token),
                    };

                    const response = await csrfFetch(`/exercises/${this.exercise.id}/attempts/${attemptId}/guidance/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(payload),
                    });

                    if (!response.ok) {
                        throw new Error(`Server returned an error: ${response.statusText}`);
                    }

                    const result = await response.json();

                    // @ts-ignore
                    const chatbotPanel = this.$refs.chatbotPanel as any;
                    if (!chatbotPanel) return;

                    if (result.user_submission) {
                        chatbotPanel.displayMessage(result.user_submission);
                    }
                    if (result.guidance) {
                        let guidanceText = result.guidance;
                        if (guidanceText.includes('<exercise_completed>')) {
                            // Confetti is now handled by the chatbot panel
                        }
                        const assistantMsg: any = { role: 'assistant', content: guidanceText };
                        if (result.assistant_trace_id) assistantMsg.trace_id = result.assistant_trace_id;
                        if (result.thoughts) assistantMsg.thoughts = result.thoughts;
                        if (result.assistant_images) assistantMsg.assistant_images = result.assistant_images;
                        chatbotPanel.displayMessage(assistantMsg);
                    }
                    
                    // Clear pending images after successful submission
                    this.pendingImages = [];
                } catch (error) {
                    this.queryError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
                }
            },
            submitAnswer() {
                // Mark that student has submitted for quiz mode
                (window as any).hasAlreadySubmittedThisQuestion = true;
                
                if (!this.userAnswer.trim() && this.pendingImages.length === 0) {
                    this.queryError = 'Please enter your answer or upload an image before submitting.';
                    return;
                }
                this.queryError = null;
                
                // Stop polling for more photos since answer is being submitted
                this.stopPolling();
                
                this.getGuidance('submit_answer');
            },
            giveHint() {
                this.queryError = null;
                this.getGuidance('ask_hint');
            },
            handleQuestion(question: string) {
                this.getGuidance('ask_question', { question });
            },

            async showUploadModal() {
                try {
                    console.log('[Upload] Requesting upload token...');
                    const response = await csrfFetch(`/exercises/image/upload-token/`, {
                        method: 'POST'
                    });
                    
                    if (!response.ok) {
                        throw new Error('Failed to get upload token');
                    }

                    const data = await response.json();
                    console.log('[Upload] Received token:', data.token);
                    this.uploadToken = data.token;
                    this.qrCodeDataUri = data.qr_code_data_uri;
                    this.showQRModal = true;
                    console.log('[Upload] Starting polling...');
                    this.startPolling();
                } catch (error) {
                    console.error('Error getting upload token:', error);
                    this.queryError = 'Failed to initialize image upload.';
                }
            },

            closeUploadModal() {
                this.showQRModal = false;
                this.qrCodeDataUri = null;
                this.stopPolling();
            },

            startPolling() {
                console.log('[Polling] Starting polling, uploadToken:', this.uploadToken);
                this.isPolling = true;
                this.pollingInterval = window.setInterval(async () => {
                    console.log('[Polling] Interval fired, uploadToken:', this.uploadToken, 'isPolling:', this.isPolling);
                    if (!this.uploadToken) {
                        console.log('[Polling] No uploadToken, stopping polling');
                        this.stopPolling();
                        return;
                    }

                    try {
                        console.log('[Polling] Checking status for token:', this.uploadToken);
                        const response = await csrfFetch(`/exercises/image/image-status/${this.uploadToken}/`);
                        if (!response.ok) {
                            console.error('[Polling] Status check failed:', response.status, response.statusText);
                            throw new Error('Failed to check upload status');
                        }

                        const data = await response.json();
                        console.log('[Polling] Status response:', data);
                        if (data.status === 'completed') {
                            console.log('[Polling] Upload completed! Adding to pendingImages');
                            this.pendingImages.push({
                                image_token: this.uploadToken!,
                                url: `/exercises/image/${this.uploadToken}`
                            });
                            
                            if (data.next_token) {
                                // Continue polling for next photo in chain silently
                                console.log('[Polling] Next token available, continuing chain:', data.next_token);
                                this.uploadToken = data.next_token;
                                // Close modal but keep polling
                                this.showQRModal = false;
                                this.qrCodeDataUri = null;
                            } else {
                                // No more photos expected in chain
                                console.log('[Polling] No next token, stopping chain');
                                this.uploadToken = null;
                                // Close modal and stop polling
                                this.closeUploadModal();
                            }
                        }
                    } catch (error) {
                        console.error('[Polling] Error checking upload status:', error);
                    }
                }, 2000); // Poll every 2 seconds
                console.log('[Polling] setInterval created with ID:', this.pollingInterval);
            },

            stopPolling() {
                console.log('[Polling] Stopping polling, interval ID:', this.pollingInterval);
                this.isPolling = false;
                if (this.pollingInterval !== null) {
                    window.clearInterval(this.pollingInterval);
                    this.pollingInterval = null;
                }
            },

            removePendingImage(index: number) {
                this.pendingImages.splice(index, 1);
            }
        },
        components: {
            'chatbot-panel': ChatbotPanel,
        },
        watch: {
            userAnswer(newValue: string) {
                const persistenceKey = `open_question_${this.exercise.id}`;
                try {
                    localStorage.setItem(persistenceKey, newValue);
                } catch (e) {
                    console.warn('Error saving answer to localStorage', e);
                }
            }
        },
        
        beforeUnmount() {
            this.stopPolling();
        }
    });

    createApp(OpenQuestionApp).mount('#openq-exercise-app');
});


