// Question Generator Vue App
import { defineComponent, ref, onMounted, nextTick, watch } from 'vue';
import { createApp } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';

// Configure marked for math rendering
marked.use({
    extensions: [{
        name: 'math',
        level: 'inline',
        start(src: string) { return src.indexOf('$'); },
        tokenizer(src: string) {
            const match = src.match(/^\$([^\$]+)\$/);
            if (match) {
                return {
                    type: 'math',
                    raw: match[0],
                    text: match[1]
                };
            }
        },
        renderer(token: any) {
            return katex.renderToString(token.text, { throwOnError: false });
        }
    }, {
        name: 'mathBlock',
        level: 'block',
        start(src: string) { return src.indexOf('$$'); },
        tokenizer(src: string) {
            const match = src.match(/^\$\$([^\$]+)\$\$/);
            if (match) {
                return {
                    type: 'mathBlock',
                    raw: match[0],
                    text: match[1]
                };
            }
        },
        renderer(token: any) {
            return '<div class="math-block">' + katex.renderToString(token.text, { 
                throwOnError: false,
                displayMode: true 
            }) + '</div>';
        }
    }]
});

interface Message {
    role: 'user' | 'assistant' | 'system';
    content: string;
}

interface UploadedFile {
    id: number;
    filename: string;
}

const GeneratorApp = defineComponent({
    delimiters: ['[[', ']]'],
    setup() {
        const sessionId = ref<string>('');
        const messages = ref<Message[]>([]);
        const userMessage = ref('');
        const uploadedFiles = ref<UploadedFile[]>([]);
        const isWaitingForAI = ref(false);
        const isBuilding = ref(false);
        const isProcessing = ref(false);
        const canBuildExercises = ref(false);
        const chatContainer = ref<HTMLElement | null>(null);
        const fileInput = ref<HTMLInputElement | null>(null);

        // Get CSRF token
        function getCsrfToken(): string {
            const token = document.querySelector('[name=csrfmiddlewaretoken]') as HTMLInputElement;
            return token ? token.value : '';
        }

        // Render markdown with math support
        function renderMarkdown(text: string): string {
            const html = marked.parse(text) as string;
            return DOMPurify.sanitize(html);
        }

        // Scroll chat to bottom
        function scrollToBottom() {
            nextTick(() => {
                if (chatContainer.value) {
                    chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
                }
            });
        }

        // Load conversation history
        async function loadConversation() {
            if (!sessionId.value) return;

            try {
                const response = await fetch(`/teacher/authoring-assistant/session/${sessionId.value}/traces/`, {
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    }
                });

                if (response.ok) {
                    const data = await response.json();
                    messages.value = data.messages || [];
                    uploadedFiles.value = data.files || [];
                    
                    // Add welcome message if no messages
                    if (messages.value.length === 0) {
                        messages.value.push({
                            role: 'assistant',
                            content: "Hi! I can help you create exercises. What would you like to build?"
                        });
                    }
                    
                    scrollToBottom();
                }
            } catch (error) {
                console.error('Failed to load conversation:', error);
            }
        }

        // Send message
        async function sendMessage() {
            const message = userMessage.value.trim();
            
            // Allow sending if either there's a message OR files have been uploaded
            if ((!message && uploadedFiles.value.length === 0) || !sessionId.value || isProcessing.value) return;

            // If no message but files uploaded, use default message
            const messageToSend = message || 'I have uploaded some files. Please analyze them and help me create exercises.';
            
            // Add user message to UI only if there's actual text from user
            if (message) {
                messages.value.push({
                    role: 'user',
                    content: message
                });
            }
            userMessage.value = '';
            isWaitingForAI.value = true;
            isProcessing.value = true;
            scrollToBottom();

            try {
                const response = await fetch(`/teacher/authoring-assistant/session/${sessionId.value}/message/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({
                        message: messageToSend
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    // Add AI response
                    messages.value.push({
                        role: 'assistant',
                        content: data.assistant_message
                    });
                    
                    // Enable build button after first exchange
                    canBuildExercises.value = true;
                } else {
                    // Show error in chat
                    messages.value.push({
                        role: 'system',
                        content: `Error: ${data.error || 'Failed to send message'}`
                    });
                }
            } catch (error) {
                console.error('Failed to send message:', error);
                messages.value.push({
                    role: 'system',
                    content: 'Error: Failed to communicate with server'
                });
            } finally {
                isWaitingForAI.value = false;
                isProcessing.value = false;
                scrollToBottom();
            }
        }

        // Handle file upload
        async function handleFileUpload(event: Event) {
            const input = event.target as HTMLInputElement;
            const files = input.files;
            if (!files || files.length === 0 || !sessionId.value || isProcessing.value) return;

            isProcessing.value = true;

            try {
                // Upload each file sequentially
                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    const formData = new FormData();
                    formData.append('file', file);

                    const response = await fetch(`/teacher/authoring-assistant/session/${sessionId.value}/upload/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: formData
                    });

                    const data = await response.json();

                    if (!response.ok) {
                        alert(`Failed to upload ${file.name}: ${data.error || 'Unknown error'}`);
                        continue; // Continue with next file
                    }
                }
                
                // After all uploads, reload the file list to show everything
                await loadConversation();
                
            } catch (error) {
                console.error('Failed to upload files:', error);
                alert('Failed to upload files');
            } finally {
                isProcessing.value = false;
                // Reset file input
                if (fileInput.value) {
                    fileInput.value.value = '';
                }
            }
        }

        // Confirm and delete file
        function confirmDeleteFile(file: UploadedFile) {
            if (confirm(`Remove ${file.filename} from context?`)) {
                deleteFile(file);
            }
        }

        // Delete file
        async function deleteFile(file: UploadedFile) {
            if (isProcessing.value) return;

            isProcessing.value = true;

            try {
                const response = await fetch(`/teacher/authoring-assistant/session/${sessionId.value}/file/${file.id}/delete/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    }
                });

                if (response.ok) {
                    // Remove from list
                    uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== file.id);
                } else {
                    const data = await response.json();
                    alert(`Failed to delete file: ${data.error || 'Unknown error'}`);
                }
            } catch (error) {
                console.error('Failed to delete file:', error);
                alert('Failed to delete file');
            } finally {
                isProcessing.value = false;
            }
        }

        // Build exercises
        async function buildExercises() {
            if (!sessionId.value || isProcessing.value || !canBuildExercises.value) return;

            isBuilding.value = true;
            isProcessing.value = true;

            try {
                // Create abort controller with 5 minute timeout
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 5 * 60 * 1000);

                const response = await fetch(`/teacher/authoring-assistant/session/${sessionId.value}/build/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({}),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);
                const data = await response.json();

                if (response.ok) {
                    if (data.stay_on_chat) {
                        // Error - stay on chat page
                        isBuilding.value = false;
                        isProcessing.value = false;
                        
                        messages.value.push({
                            role: 'assistant',
                            content: data.error
                        });
                        scrollToBottom();
                    } else {
                        // Success - redirect to review
                        window.location.href = data.redirect_url;
                    }
                } else {
                    isBuilding.value = false;
                    isProcessing.value = false;
                    alert(`Failed to build exercises: ${data.error || 'Unknown error'}`);
                }
            } catch (error) {
                console.error('Failed to build exercises:', error);
                isBuilding.value = false;
                isProcessing.value = false;
                
                if (error instanceof Error && error.name === 'AbortError') {
                    alert('Request timed out after 5 minutes. The AI may be processing a large amount of content. Please try again or simplify your request.');
                } else {
                    alert('Failed to build exercises');
                }
            }
        }

        // Initialize
        onMounted(() => {
            const sessionInput = document.getElementById('session-id') as HTMLInputElement;
            
            if (sessionInput && sessionInput.value) {
                sessionId.value = sessionInput.value;
                loadConversation();
            }
        });
        
        // Watch messages to update state
        watch(messages, (newMessages) => {
            if (newMessages.length > 1) {  // More than just welcome message
                canBuildExercises.value = true;
            }
        });

        return {
            sessionId,
            messages,
            userMessage,
            uploadedFiles,
            isWaitingForAI,
            isBuilding,
            isProcessing,
            canBuildExercises,
            chatContainer,
            fileInput,
            renderMarkdown,
            sendMessage,
            handleFileUpload,
            confirmDeleteFile,
            buildExercises
        };
    }
});

// Mount app
const app = createApp(GeneratorApp);
app.mount('#generator-app');
