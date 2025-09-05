import { ChatbotPanel } from './ChatbotPanel.js';
import { CodeMirrorEditor } from './CodeMirrorEditor.js';
import { createApp, defineComponent } from 'vue';
import confetti from 'canvas-confetti';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import type { Exercise } from './utils.js';
import { csrfFetch, getCsrfToken } from './utils.js';

interface ScalaDataContext {
    exercise: Exercise;
    userCode: string;
    executionOutput: string | null;
    executionError: string | null;
    loadingState: 'idle' | 'executing' | 'getting-guidance';
    durationMs: number | null;
    start_timestamp: string;
}

interface OptionButton { id: string; title: string; comment?: string; to?: string; }

document.addEventListener('DOMContentLoaded', function() {
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('scala-exercise-app');

    if (!exerciseDataScript || !appElement) {
        console.error('Required script tags or app element not found!');
        return;
    }
    const exerciseData: Exercise = JSON.parse(exerciseDataScript.textContent || '{}');

    const attemptIdScript = document.getElementById('attempt-id');
    let attemptId: number | null = null;
    if (attemptIdScript && attemptIdScript.textContent) {
        attemptId = JSON.parse(attemptIdScript.textContent);
    }

    const interactionsScript = document.getElementById('interactions-data');
    let initialMessages: any[] = [];
    let lastUserCode = '';
    if (interactionsScript) {
        const logs = JSON.parse(interactionsScript.textContent || '[]') as any[];
        for (let i = logs.length - 1; i >= 0; i--) {
            const log = logs[i];
            if (log.user_submission && log.user_submission.metadata && log.user_submission.metadata.code) {
                lastUserCode = log.user_submission.metadata.code;
                break;
            }
        }
        logs.forEach((log: any) => {
            if (log.user_submission) initialMessages.push(log.user_submission);
            if (log.llm_response) initialMessages.push(log.llm_response);
        });
    }

    const ScalaExerciseApp = defineComponent({
        delimiters: ['[[', ']]'],
        data(): ScalaDataContext {
            return {
                exercise: exerciseData,
                userCode: lastUserCode || (exerciseData.exercise_data && exerciseData.exercise_data.answer_template) || '',
                executionOutput: null,
                executionError: null,
                loadingState: 'idle',
                durationMs: null,
                start_timestamp: new Date().toISOString(),
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

            if (chatbotPanel) {
                initialMessages.forEach(msg => chatbotPanel.displayMessage(msg));
            }
        },
        methods: {
            renderMarkdown(this: any, content: string) {
                if (!content) return '';
                return DOMPurify.sanitize(marked.parse(content) as string);
            },
            async getGuidance(action: 'run_submission' | 'ask_hint' | 'ask_question' | 'option_selected', details: { question?: string | null, error?: string | null, output?: string | null, selected_option?: OptionButton } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    const csrfToken = getCsrfToken();
                    const payload = {
                        action,
                        code: this.userCode,
                        output: details.output,
                        question: details.question || null,
                        error_message: details.error || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString(),
                        selected_option: details.selected_option || null,
                    };
                    const response = await csrfFetch(`/exercises/${this.exercise.id}/attempts/${attemptId}/guidance/`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    if (!response.ok) throw new Error(`Server returned an error: ${response.statusText}`);
                    const result = await response.json();
                    
                    // @ts-ignore
                    const chatbotPanel = this.$refs.chatbotPanel as any;
                    if (!chatbotPanel) return;

                    if (result.user_submission) chatbotPanel.displayMessage(result.user_submission);
                    if (result.guidance) {
                        let guidanceText = result.guidance as string;
                        if (guidanceText.includes('<exercise_completed>')) {
                            // Confetti is now handled by the chatbot panel
                            this.updateStatusIcon();
                        }
                        chatbotPanel.displayMessage({ role: 'assistant', content: guidanceText });
                    }
                } catch (error) {
                    this.executionError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
                }
            },
            async runCode() {
                if (!this.userCode.trim()) {
                    this.executionError = 'Please enter some code';
                    return;
                }
                try {
                    this.loadingState = 'executing';
                    this.executionError = null;
                    this.executionOutput = null;
                    this.durationMs = null;

                    const response = await csrfFetch('/exercises/api/scala/execute/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code: this.userCode }),
                    });
                    const result = await response.json();
                    this.durationMs = typeof result.durationMs === 'number' ? result.durationMs : null;
                    if (result.success) {
                        this.executionOutput = (result.output || '').trim();
                        await (this as any).$nextTick();
                        await this.getGuidance('run_submission', { output: this.executionOutput });
                    } else {
                        const errorMessage = String(result.error || 'Unknown error');
                        this.executionError = errorMessage;
                        await (this as any).$nextTick();
                        await this.getGuidance('run_submission', { error: errorMessage });
                    }
                } catch (error) {
                    const errorMessage = String(error);
                    this.executionError = errorMessage;
                    await (this as any).$nextTick();
                    await this.getGuidance('run_submission', { error: errorMessage });
                } finally {
                    this.loadingState = 'idle';
                }
            },
            giveHint() { this.getGuidance('ask_hint'); },
            handleQuestion(question: string) { this.getGuidance('ask_question', { question }); },
            handleOptionSelected(option: OptionButton) {
                if (option.to) {
                    if (/^\d+$/.test(option.to)) {
                        window.location.href = `/exercises/${option.to}/`;
                    }
                } else {
                    this.getGuidance('option_selected', { selected_option: option });
                }
            },
            updateStatusIcon() {
                const iconContainer = document.getElementById('exercise-status-icon');
                if (!iconContainer) return;
                const existingIcon = iconContainer.querySelector('i');
                if (existingIcon) {
                    existingIcon.className = 'fas fa-check-circle has-text-success';
                    existingIcon.setAttribute('title', 'Completed');
                    existingIcon.setAttribute('aria-label', 'Completed');
                } else {
                    iconContainer.innerHTML = '<i class="fas fa-check-circle has-text-success" title="Completed" aria-label="Completed"></i>';
                }
            },
        },
        components: { 'chatbot-panel': ChatbotPanel, 'code-mirror-editor': CodeMirrorEditor },
    });

    createApp(ScalaExerciseApp).mount('#scala-exercise-app');
});


