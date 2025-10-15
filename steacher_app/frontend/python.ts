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

interface PythonDataContext {
    exercise: Exercise;
    userCode: string;
    executionOutput: string | null;
    executionError: string | null;
    consoleHistory: ConsoleEntry[];
    currentCommand: string;
    commandHistory: string[];
    commandHistoryIndex: number;
    loadingState: 'idle' | 'pyodide-loading' | 'executing' | 'getting-guidance';
    worker: Worker | null;
    workerReady: boolean;
    pendingResolvers: { [runId: string]: (value: any) => void };
    executionTimeoutMs: number;
    staticPrefix: string;
    start_timestamp: string;
}

document.addEventListener('DOMContentLoaded', function() {
    // Get exercise data from JSON script tag
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('python-exercise-app');

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
    let lastUserCode = '';
    if (interactionsScript) {
        const logs = JSON.parse(interactionsScript.textContent || '[]') as any[];

        // Find the last code submission from the logs
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

    // Main Vue app
    const PythonExerciseApp = defineComponent({
        delimiters: ['[[', ']]'],
        data(): PythonDataContext {
            const datasetEl = appElement as HTMLElement;
            const staticPrefix = datasetEl?.getAttribute('data-static-prefix') || '/static/';
            const timeoutAttr = datasetEl?.getAttribute('data-execution-timeout');
            const executionTimeoutMs = timeoutAttr ? parseInt(timeoutAttr, 10) : 8000;
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
                worker: null,
                workerReady: false,
                pendingResolvers: {},
                executionTimeoutMs,
                staticPrefix,
                start_timestamp: new Date().toISOString()
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

            await this.startWorker();
            
            // Expose for quiz mode auto-submit
            (window as any).submitAnswer = () => this.submitAnswer();
        },
        
        methods: {
            renderMarkdown(this: any, content: string) {
                if (!content) return '';
                return DOMPurify.sanitize(marked.parse(content) as string);
            },
            async startWorker() {
                try {
                    this.loadingState = 'pyodide-loading';
                    // Create a module worker from the built JS path under static
                    const cacheBust = Date.now();
                    const workerUrl = `${this.staticPrefix}js/dist/python_worker.js?v=${cacheBust}`;
                    const w = new Worker(workerUrl, { type: 'module' });
                    this.worker = w;

                    w.onmessage = (evt: MessageEvent) => {
                        const msg = evt.data as any;
                        if (!msg || !msg.type) return;
                        if (msg.type === 'ready') {
                            this.workerReady = true;
                            this.loadingState = 'idle';
                            return;
                        }
                        if (msg.type === 'init-error') {
                            this.executionError = 'Failed to initialize Python interpreter: ' + String(msg.error);
                            this.loadingState = 'idle';
                            return;
                        }
                        if (msg.type === 'result') {
                            const { runId } = msg;
                            const resolver = this.pendingResolvers[runId];
                            if (resolver) {
                                resolver(msg);
                                delete this.pendingResolvers[runId];
                            }
                            return;
                        }
                    };

                    // Initialize pyodide inside the worker using local static files, with cache-busting
                    const pyodideModuleUrl = `https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs?v=${cacheBust}`;
                    const indexURL = `https://cdn.jsdelivr.net/pyodide/v0.28.3/full/`;
                    w.postMessage({ type: 'init', pyodideModuleUrl, indexURL });
                } catch (error) {
                    console.error('Failed to start worker:', error);
                    this.executionError = 'Failed to start Python worker: ' + String(error);
                    this.loadingState = 'idle';
                }
            },
            async getGuidance(action: 'run_submission' | 'ask_hint' | 'ask_question', details: { question?: string | null, error?: string | null, output?: string | null } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    const csrfToken = getCsrfToken();

                    const payload = {
                        action: action,
                        code: this.userCode,
                        output: details.output,
                        question: details.question || null,
                        error_message: details.error || null,
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
                    
                    // @ts-ignore
                    const chatbotPanel = this.$refs.chatbotPanel as any;
                    if (!chatbotPanel) return;

                    if (result.user_submission) {
                        chatbotPanel.displayMessage(result.user_submission);
                    }
                    if (result.guidance) {
                        let guidanceText = result.guidance;
                        // Confetti is now handled by the chatbot panel
                        if (guidanceText.includes('<exercise_completed>')) {
                            this.updateStatusIcon();
                        }
                        const assistantMsg: any = { role: 'assistant', content: guidanceText };
                        if (result.assistant_trace_id) assistantMsg.trace_id = result.assistant_trace_id;
                        if (result.thoughts) assistantMsg.thoughts = result.thoughts;
                        chatbotPanel.displayMessage(assistantMsg);
                    }
                } catch (error) {
                    this.executionError = `Error communicating with the server: ${error}`;
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

            async executeCode(code: string) {
                if (!this.worker || !this.workerReady) {
                    this.executionError = 'Python worker not ready yet. Please wait...';
                    return;
                }

                try {
                    this.loadingState = 'executing';
                    this.executionError = null;
                    this.executionOutput = null;
                    const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
                    const resultPromise = new Promise((resolve) => {
                        this.pendingResolvers[runId] = resolve as (value: any) => void;
                    }) as Promise<any>;

                    this.worker.postMessage({ type: 'run', runId, code });

                    let timedOut = false;
                    const timeoutHandle = setTimeout(() => {
                        timedOut = true;
                        try {
                            this.worker?.terminate();
                        } catch (_) { /* noop */ }
                        this.worker = null;
                        this.workerReady = false;
                        this.executionError = `Execution timed out after ${this.executionTimeoutMs / 1000} seconds (possible infinite loop).`;
                        this.consoleHistory.push({ type: 'error', content: this.executionError });
                        const resolver = this.pendingResolvers[runId];
                        if (resolver) {
                            resolver({ success: false, error: this.executionError });
                        }
                        delete this.pendingResolvers[runId];
                    }, this.executionTimeoutMs);

                    const msg = await resultPromise.catch((e) => ({ error: String(e), success: false }));
                    clearTimeout(timeoutHandle);

                    if (!timedOut) {
                        if (msg.success) {
                            this.executionOutput = (msg.stdout || '').trim();
                            if (this.executionOutput) {
                                this.consoleHistory.push({ type: 'output', content: this.executionOutput });
                            }
                        } else {
                            const errorMessage = String(msg.error || 'Unknown error');
                            const cleanedError = this.cleanConsoleError(errorMessage);
                            this.executionError = cleanedError;
                            this.consoleHistory.push({ type: 'error', content: cleanedError });
                        }
                    }

                } catch (error) {
                    const errorMessage = String(error);
                    const cleanedError = this.cleanConsoleError(errorMessage);
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
                
                // Restart worker if it was terminated due to timeout
                if (!this.workerReady && !this.worker) {
                    await this.startWorker();
                }
            },
            
            giveHint() {
                this.getGuidance('ask_hint', { error: this.executionError, output: this.executionOutput });
            },
            
            handleQuestion(question: string) {
                this.getGuidance('ask_question', { question, error: this.executionError, output: this.executionOutput });
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
                // For simple expressions, wrap with print() to show the result
                let processedCommand = command;
                if (this.isSimpleExpression(command)) {
                    processedCommand = `print(${command})`;
                }
                const combinedCode = this.userCode + '\n\n# Console command:\n' + processedCommand;
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

            isSimpleExpression(command: string): boolean {
                // Check if it's a simple expression that should be auto-printed
                const trimmed = command.trim();

                // Skip if it's already a statement (contains keywords, assignments, etc.)
                if (trimmed.includes('print(') ||
                    trimmed.includes('=') ||
                    trimmed.startsWith('if ') ||
                    trimmed.startsWith('for ') ||
                    trimmed.startsWith('while ') ||
                    trimmed.startsWith('def ') ||
                    trimmed.startsWith('class ') ||
                    trimmed.startsWith('import ') ||
                    trimmed.startsWith('from ')) {
                    return false;
                }

                // Auto-print simple expressions like variable names, function calls, math expressions
                return true;
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

        },
        components: {
            'chatbot-panel': ChatbotPanel,
            'code-mirror-editor': CodeMirrorEditor
        }
    });

    createApp(PythonExerciseApp).mount('#python-exercise-app');
}); 