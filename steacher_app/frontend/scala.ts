import { ChatbotPanel } from './ChatbotPanel.js';
import { CodeMirrorEditor } from './CodeMirrorEditor.js';
import { createApp, defineComponent } from 'vue';
import confetti from 'canvas-confetti';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import type { Exercise } from './utils.js';
import { csrfFetch, getCsrfToken } from './utils.js';

interface ConsoleEntry {
    type: 'command' | 'output' | 'error';
    content: string;
}

interface ScalaDataContext {
    exercise: Exercise;
    userCode: string;
    executionOutput: string | null;
    executionError: string | null;
    consoleHistory: ConsoleEntry[];
    currentCommand: string;
    commandHistory: string[];
    commandHistoryIndex: number;
    loadingState: 'idle' | 'executing' | 'getting-guidance';
    start_timestamp: string;
}

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
                consoleHistory: [],
                currentCommand: '',
                commandHistory: [],
                commandHistoryIndex: -1,
                loadingState: 'idle',
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
            
            // Expose for quiz mode auto-submit
            (window as any).submitAnswer = () => this.submitAnswer();
        },
        methods: {
            stripAnsi(this: any, text: string | null | undefined) {
                if (!text) return '';
                // Remove ANSI color codes like \u001b[31m
                return String(text).replace(/\u001b\[[0-9;]*m/g, '');
            },
            cleanScalaOutput(this: any, text: string | null | undefined) {
                const cleaned = this.stripAnsi(text || '');
                const lines = cleaned.replace(/\r\n/g, '\n').replace(/\r/g, '').split('\n');
                const resultLines: string[] = [];
                for (let line of lines) {
                    if (/^\s*Compiling\b/.test(line)) {
                        continue;
                    }
                    // Remove leading cmdN.sc:X: prefix
                    line = line.replace(/^cmd\d+\.sc:\d+:\s*/, '');
                    resultLines.push(line);
                }
                // Trim leading/trailing empty lines
                while (resultLines.length > 0 && ((resultLines[0] || '').trim() === '')) resultLines.shift();
                while (resultLines.length > 0 && (((resultLines[resultLines.length - 1]) || '').trim() === '')) resultLines.pop();
                return resultLines.join('\n');
            },
            renderMarkdown(this: any, content: string) {
                if (!content) return '';
                return DOMPurify.sanitize(marked.parse(content) as string);
            },
            async getGuidance(action: 'run_submission' | 'ask_hint' | 'ask_question', details: { question?: string | null, error?: string | null, output?: string | null } = {}) {
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
                        const assistantMsg: any = { role: 'assistant', content: guidanceText };
                        if (result.assistant_trace_id) assistantMsg.trace_id = result.assistant_trace_id;
                        chatbotPanel.displayMessage(assistantMsg);
                    }
                } catch (error) {
                    this.executionError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
                }
            },
            async executeCode(code: string) {
                try {
                    this.loadingState = 'executing';
                    this.executionError = null;
                    this.executionOutput = null;

                    const response = await csrfFetch('/exercises/api/scala/execute/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code }),
                    });
                    const result = await response.json();
                    if (result.success) {
                        this.executionOutput = this.cleanScalaOutput(result.output || '');
                        this.executionError = null;
                        if (this.executionOutput) {
                            this.consoleHistory.push({ type: 'output', content: this.executionOutput });
                        }
                    } else {
                        const outputText = this.cleanScalaOutput(result.output || result.error || 'Unknown error');
                        const cleanedError = this.cleanConsoleError(outputText);
                        this.executionOutput = cleanedError;
                        this.executionError = cleanedError;
                        this.consoleHistory.push({ type: 'error', content: cleanedError });
                    }
                } catch (error) {
                    const errorMessage = this.cleanScalaOutput(String(error));
                    const cleanedError = this.cleanConsoleError(errorMessage);
                    this.executionOutput = cleanedError;
                    this.executionError = cleanedError;
                    this.consoleHistory.push({ type: 'error', content: cleanedError });
                } finally {
                    this.loadingState = 'idle';
                }
            },

            async submitAnswer() {
                // Mark that student has submitted for quiz mode
                (window as any).hasAlreadySubmittedThisQuestion = true;
                
                if (!this.userCode.trim()) {
                    this.executionError = 'Please enter some code';
                    return;
                }

                await this.executeCode(this.userCode);

                // Submit results to guidance
                await (this as any).$nextTick();
                if (this.executionError) {
                    await this.getGuidance('run_submission', { error: this.executionError });
                } else {
                    await this.getGuidance('run_submission', { output: this.executionOutput });
                }
            },

            async executeConsoleCommand() {
                if (!this.currentCommand.trim()) {
                    return;
                }

                const command = this.currentCommand.trim();

                // Add command to history
                this.consoleHistory.push({ type: 'command', content: command });
                this.commandHistory.push(command);
                this.commandHistoryIndex = -1;

                // Clear current command
                this.currentCommand = '';

                // Execute the command in context of main code
                const combinedCode = this.userCode + '\n\n// Console command:\n' + command;
                await this.executeCode(combinedCode);

                // Scroll to bottom and focus input
                await (this as any).$nextTick();
                this.scrollConsoleToBottom();
                this.focusConsoleInput();
            },

            previousCommand() {
                if (this.commandHistory.length === 0) return;

                if (this.commandHistoryIndex === -1) {
                    this.commandHistoryIndex = this.commandHistory.length - 1;
                } else if (this.commandHistoryIndex > 0) {
                    this.commandHistoryIndex--;
                }

                this.currentCommand = this.commandHistory[this.commandHistoryIndex] || '';
            },

            nextCommand() {
                if (this.commandHistory.length === 0) return;

                if (this.commandHistoryIndex < this.commandHistory.length - 1) {
                    this.commandHistoryIndex++;
                    this.currentCommand = this.commandHistory[this.commandHistoryIndex] || '';
                } else {
                    this.commandHistoryIndex = -1;
                    this.currentCommand = '';
                }
            },

            scrollConsoleToBottom() {
                const container = document.querySelector('.console-container');
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            },

            focusConsoleInput() {
                const input = this.$refs.consoleInput as HTMLInputElement;
                if (input) {
                    input.focus();
                }
            },

            cleanConsoleError(errorMessage: string): string {
                // Filter out confusing File "<exec>" lines but keep the actual error
                const lines = errorMessage.split('\n');
                const filteredLines = lines.filter(line =>
                    !line.trim().startsWith('File "<exec>"') &&
                    line.trim() !== ''
                );
                return filteredLines.join('\n').trim() || errorMessage;
            },
            giveHint() { this.getGuidance('ask_hint', { error: this.executionError, output: this.executionOutput }); },
            handleQuestion(question: string) { this.getGuidance('ask_question', { question, error: this.executionError, output: this.executionOutput }); },
            
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


