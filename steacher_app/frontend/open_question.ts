import { ChatbotPanel } from './ChatbotPanel.js';
import { createApp, defineComponent } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import confetti from 'canvas-confetti';
import type { Exercise } from './utils.js';
import { csrfFetch, getCsrfToken } from './utils.js';

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
            return {
                exercise: exerciseData,
                userAnswer: lastAnswer || (exerciseData.exercise_data && exerciseData.exercise_data.answer_template) || '',
                queryError: null,
                loadingState: 'idle',
                chatMessages: initialMessages,
                start_timestamp: new Date().toISOString(),
            };
        },
        methods: {
            renderMarkdown(this: any, content: string) {
                if (!content) return '';
                return DOMPurify.sanitize(marked.parse(content) as string);
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


