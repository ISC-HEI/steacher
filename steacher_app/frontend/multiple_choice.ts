import { ChatbotPanel } from './ChatbotPanel.js';
import { createApp, defineComponent } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import confetti from 'canvas-confetti';
import type { Exercise } from './utils.js';
import { csrfFetch, getCsrfToken } from './utils.js';

interface Choice {
    id: string;
    text: string;
}

interface Selections {
    [key: string]: 'right' | 'wrong' | 'notsure' | null;
}

interface MultipleChoiceDataContext {
    exercise: Exercise;
    selections: Selections;
    justification: string;
    queryError: string | null;
    loadingState: 'idle' | 'getting-guidance';
    guidance: string | null;
    start_timestamp: string;
    isSubmitted: boolean;
    feedback: any | null; // Will hold the CBM result from the backend
}

document.addEventListener('DOMContentLoaded', function() {
    // Get exercise data from JSON script tag
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('mc-exercise-app');

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
    let lastSelections: Selections | null = null;
    let lastJustification: string = '';
    let isAlreadySubmitted = false;
    let initialFeedback = null;

    if (interactionsScript) {
        const logs = JSON.parse(interactionsScript.textContent || '[]') as any[];
        
        // Find the last answer submission from the logs to restore state
        const lastSubmissionLog = logs.slice().reverse().find(log => 
            log.user_submission && 
            log.user_submission.metadata && 
            log.user_submission.metadata.action === 'submit_answer'
        );

        if (lastSubmissionLog) {
            const metadata = lastSubmissionLog.user_submission.metadata;
            lastSelections = metadata.selections;
            lastJustification = metadata.justification || '';
            isAlreadySubmitted = true;
            // Also restore the feedback object from the submission log
            if (metadata.cbm_result) {
                initialFeedback = metadata.cbm_result;
            }
        }

        logs.forEach((log: any) => {
            if (log.user_submission) initialMessages.push(log.user_submission);
            if (log.llm_response) initialMessages.push(log.llm_response);
        });
    }

    // Main Vue app
    const MultipleChoiceExerciseApp = defineComponent({
        delimiters: ['[[', ']]'],
        data(): MultipleChoiceDataContext {
            // Initialize selections object with null values for each choice
            const initialSelections: Selections = {};
            exerciseData.exercise_data.choices.forEach(choice => {
                initialSelections[choice.id] = null;
            });

            return {
                exercise: exerciseData,
                selections: lastSelections || initialSelections,
                justification: lastJustification,
                queryError: null as string | null,
                loadingState: 'idle', // 'idle', 'getting-guidance'
                guidance: null,
                start_timestamp: new Date().toISOString(),
                isSubmitted: isAlreadySubmitted,
                feedback: initialFeedback
            }
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
        },

        computed: {
            allChoicesSelected(): boolean {
                // Check if a selection has been made for every choice
                return Object.values(this.selections).every(selection => selection !== null);
            }
        },
        
        methods: {
            renderMarkdown(this: any, content: string) {
                if (!content) return '';
                return DOMPurify.sanitize(marked.parse(content) as string);
            },
            getChoiceClass(choiceId: string, confidenceValue: 'right' | 'wrong' | 'notsure') {
                if (!this.feedback) return '';

                const choiceFeedback = this.feedback.breakdown[choiceId];
                if (!choiceFeedback) return '';

                const isCorrectOption = choiceFeedback.actual_status.toUpperCase() === 'CORRECT';
                const correctConfidence = isCorrectOption ? 'right' : 'wrong';

                // Was the student's selection for this specific radio button correct?
                if (confidenceValue === correctConfidence) {
                    return 'is-correct-choice';
                }
                
                // Was the student's overall selection for this option incorrect?
                if (this.selections[choiceId] !== correctConfidence) {
                    // And is this the radio button they wrongly selected?
                    if (this.selections[choiceId] === confidenceValue) {
                        return 'is-incorrect-choice';
                    }
                }
                return '';
            },
            async getGuidance(action: 'submit_answer' | 'ask_hint' | 'ask_question', details: { question?: string | null } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    console.log(`Getting guidance for action: ${action}`);

                    const csrfToken = getCsrfToken();

                    // 2. Prepare payload
                    const payload = {
                        action: action,
                        selections: this.selections,
                        question: details.question || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString()
                    };

                    // 3. Make API call
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
                    console.log('Guidance received:', result);
                    this.guidance = result.guidance;

                    // Store feedback if it exists on the response
                    if (result.cbm_result) {
                        this.feedback = result.cbm_result;
                    }

                    // @ts-ignore
                    const chatbotPanel = this.$refs.chatbotPanel as any;
                    if (!chatbotPanel) return;

                    // Add the user submission to the chat history
                    if (result.user_submission) {
                        chatbotPanel.displayMessage(result.user_submission);
                    }
                    
                    // Add the assistant's response to the chat
                    if (result.guidance) {
                        let guidanceText = result.guidance;
                        if (guidanceText.includes('<exercise_completed>')) {
                            // Confetti is now handled by the chatbot panel
                            this.updateStatusIcon();
                        }
                        chatbotPanel.displayMessage({ role: 'assistant', content: guidanceText });

                        // If the action was submitting an answer, lock the controls
                        if (action === 'submit_answer') {
                            this.isSubmitted = true;
                        }
                    }

                } catch (error) {
                    console.error('Failed to get guidance:', error);
                    this.queryError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
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

            submitAnswer() {
                if (!this.allChoicesSelected) {
                    this.queryError = 'Please make a selection for every option.';
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
            'chatbot-panel': ChatbotPanel
        }
    });

    const app = createApp(MultipleChoiceExerciseApp);
    app.mount('#mc-exercise-app');
}); 