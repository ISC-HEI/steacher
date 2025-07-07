import { ChatbotPanel } from './ChatbotPanel.js';
import { CodeMirrorEditor } from './CodeMirrorEditor.js';
import { createApp, markRaw, defineComponent } from 'vue';
import confetti from 'canvas-confetti';
import { loadPyodide } from 'pyodide';

// Define the shape of our exercise data for type safety
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

interface PythonDataContext {
    exercise: Exercise;
    userCode: string;
    executionOutput: string | null;
    executionError: string | null;
    loadingState: 'idle' | 'pyodide-loading' | 'executing' | 'getting-guidance';
    pyodide: any | null;
    chatMessages: any[];
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

    // Get guidance logs if they exist
    const guidanceLogsScript = document.getElementById('guidance-logs-data');
    let initialMessages: any[] = [];
    let lastUserCode = '';
    if (guidanceLogsScript) {
        const logs = JSON.parse(guidanceLogsScript.textContent || '[]') as any[];

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
            return {
                exercise: exerciseData,
                userCode: lastUserCode,
                executionOutput: null,
                executionError: null,
                loadingState: 'idle',
                pyodide: null,
                chatMessages: initialMessages,
                start_timestamp: new Date().toISOString()
            }
        },
        
        async mounted() {
            await this.loadPyodideInterpreter();
        },
        
        methods: {
            async getGuidance(action: 'run_code' | 'ask_hint' | 'ask_question', details: { question?: string | null, error?: string | null, output?: string | null } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                    if (!csrfTokenElement) {
                        throw new Error('CSRF token not found!');
                    }
                    const csrfToken = csrfTokenElement.value;

                    const payload = {
                        action: action,
                        code: this.userCode,
                        output: details.output,
                        question: details.question || null,
                        error_message: details.error || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString()
                    };

                    const response = await fetch(`/exercises/${this.exercise.id}/guidance/`, {
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
                    this.executionError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
                }
            },

            async loadPyodideInterpreter() {
                try {
                    this.loadingState = 'pyodide-loading';
                    const pyodideInstance = await loadPyodide({
                        indexURL: "https://cdn.jsdelivr.net/pyodide/v0.28.0/full/"
                    });
                    this.pyodide = markRaw(pyodideInstance);
                } catch (error) {
                    console.error('Error loading Pyodide:', error);
                    this.executionError = 'Failed to load Python interpreter: ' + String(error);
                } finally {
                    this.loadingState = 'idle';
                }
            },
            
            async runCode() {
                if (!this.pyodide) {
                    this.executionError = 'Pyodide not loaded yet. Please wait...';
                    return;
                }
                
                if (!this.userCode.trim()) {
                    this.executionError = 'Please enter some code';
                    return;
                }
                
                try {
                    this.loadingState = 'executing';
                    this.executionError = null;
                    this.executionOutput = null;
                    
                    // Capture stdout
                    let stdout = '';
                    this.pyodide.setStdout({
                        batched: (msg: string) => {
                            stdout += msg + "\n";
                        }
                    });

                    await this.pyodide.loadPackagesFromImports(this.userCode);
                    await this.pyodide.runPythonAsync(this.userCode);
                    
                    this.executionOutput = stdout.trim();
                    await this.getGuidance('run_code', { output: this.executionOutput });

                } catch (error) {
                    const errorMessage = String(error);
                    this.executionError = errorMessage;
                    await this.getGuidance('run_code', { error: errorMessage });
                } finally {
                    this.loadingState = 'idle';
                }
            },
            
            giveHint() {
                this.getGuidance('ask_hint');
            },
            
            handleQuestion(question: string) {
                this.getGuidance('ask_question', { question });
            }
        },
        components: {
            'chatbot-panel': ChatbotPanel,
            'code-mirror-editor': CodeMirrorEditor
        }
    });

    createApp(PythonExerciseApp).mount('#python-exercise-app');
}); 