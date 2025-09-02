import { ChatbotPanel } from './ChatbotPanel.js';
import { createApp, defineComponent } from 'vue';
import confetti from 'canvas-confetti';

interface Exercise {
    id: number;
    title: string;
    exercise_type: string;
    description: string;
    exercise_data: {
        question: string;
        additional_context?: string;
    };
}

interface OpenQuestionDataContext {
    exercise: Exercise;
    userAnswer: string;
    queryError: string | null;
    loadingState: 'idle' | 'getting-guidance';
    chatMessages: any[];
    start_timestamp: string;
}

document.addEventListener('DOMContentLoaded', function() {
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('openq-exercise-app');

    if (!exerciseDataScript || !appElement) {
        console.error('Required script tags or app element not found!');
        return;
    }
    const exerciseData: Exercise = JSON.parse(exerciseDataScript.textContent || '{}');

    // Get trace ID from script tag
    const traceIdScript = document.getElementById('trace-id');
    let traceId: number | null = null;
    if (traceIdScript && traceIdScript.textContent) {
        traceId = JSON.parse(traceIdScript.textContent);
    }

    // Get guidance logs if they exist
    const guidanceLogsScript = document.getElementById('guidance-logs-data');
    let initialMessages: any[] = [];
    let lastAnswer = '';
    if (guidanceLogsScript) {
        const logs = JSON.parse(guidanceLogsScript.textContent || '[]') as any[];
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
            return {
                exercise: exerciseData,
                userAnswer: lastAnswer,
                queryError: null,
                loadingState: 'idle',
                chatMessages: initialMessages,
                start_timestamp: new Date().toISOString(),
            };
        },
        methods: {
            async getGuidance(action: 'submit_answer' | 'ask_hint' | 'ask_question', details: { question?: string | null } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                    if (!csrfTokenElement) {
                        this.queryError = 'Could not find CSRF token on page. Cannot contact server.';
                        return;
                    }
                    const csrfToken = csrfTokenElement.value;

                    const payload: any = {
                        action: action,
                        answer: this.userAnswer,
                        question: details.question || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString(),
                    };

                    const response = await fetch(`/exercises/${this.exercise.id}/traces/${traceId}/guidance/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken,
                        },
                        body: JSON.stringify(payload),
                    });

                    if (!response.ok) {
                        throw new Error(`Server returned an error: ${response.statusText}`);
                    }

                    const result = await response.json();
                    if (result.user_submission) {
                        this.chatMessages.push(result.user_submission);
                    }
                    if (result.guidance) {
                        let guidanceText = result.guidance;
                        if (guidanceText.includes('<exercise_completed>')) {
                            confetti({ particleCount: 200, spread: 150, origin: { y: 0.6 } });
                            guidanceText = guidanceText.replace('<exercise_completed>', '').trim();
                        }
                        this.chatMessages.push({ role: 'assistant', content: guidanceText });
                    }
                } catch (error) {
                    this.queryError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
                }
            },
            submitAnswer() {
                if (!this.userAnswer.trim()) {
                    this.queryError = 'Please enter your answer before submitting.';
                    return;
                }
                this.queryError = null;
                this.getGuidance('submit_answer');
            },
            giveHint() {
                this.queryError = null;
                this.getGuidance('ask_hint');
            },
            handleQuestion(question: string) {
                this.getGuidance('ask_question', { question });
            }
        },
        components: {
            'chatbot-panel': ChatbotPanel,
        }
    });

    createApp(OpenQuestionApp).mount('#openq-exercise-app');
});


