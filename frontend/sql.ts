import { PGlite } from '@electric-sql/pglite';
import { ChatbotPanel } from './ChatbotPanel.js';
import { CodeMirrorEditor } from './CodeMirrorEditor.js';
import { createApp, markRaw, defineComponent } from 'vue';
import confetti from 'canvas-confetti';

// Define the shape of our exercise data for type safety
interface Exercise {
    id: number;
    title: string;
    exercise_type: string;
    description: string;
    exercise_data: {
        question: string;
        additional_context?: string;
        db?: string;
        hints?: string[];
        expected_result?: Record<string, any>[];
        correct_answers?: { answer: string; explanation: string }[];
    };
}

// Define the shape for the query result for type safety
interface QueryResult {
    type: 'select' | 'modification' | 'other';
    columns?: string[];
    rows?: Record<string, any>[];
    rowCount?: number;
    affectedRows?: number;
    message?: string;
}

interface SqlDataContext {
    exercise: Exercise;
    userQuery: string;
    showHints: boolean;
    showExpectedResult: boolean;
    showCorrectAnswers: boolean;
    queryResult: QueryResult | null;
    queryError: string | null;
    loadingState: 'idle' | 'db-loading' | 'querying' | 'getting-guidance';
    database: any | null; // PGlite instance
    guidance: string | null;
    chatMessages: any[];
    start_timestamp: string;
}

document.addEventListener('DOMContentLoaded', function() {
    // Get exercise data from JSON script tag
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('sql-exercise-app');

    if (!exerciseDataScript || !appElement) {
        console.error('Required script tags or app element not found!');
        return;
    }
    const exerciseData: Exercise = JSON.parse(exerciseDataScript.textContent || '{}');
    const staticPrefix = appElement.dataset.staticPrefix || '/static/';
    const assetUrl = appElement.dataset.assetUrl || '';

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
                break; // Found the last code, so we can stop
            }
        }
        
        logs.forEach((log: any) => {
            if (log.user_submission) initialMessages.push(log.user_submission);
            if (log.llm_response) initialMessages.push(log.llm_response);
        });
    }

    // Main Vue app
    const SqlExerciseApp = defineComponent({
        delimiters: ['[[', ']]'],
        data(): SqlDataContext {
            return {
                exercise: exerciseData,
                userQuery: lastUserCode, // Initialize with the last saved code
                showHints: false,
                showExpectedResult: false,
                showCorrectAnswers: false,
                queryResult: null,
                queryError: null as string | null,
                loadingState: 'idle', // 'idle', 'db-loading', 'querying', 'getting-guidance'
                database: null,
                guidance: null,
                chatMessages: initialMessages,
                start_timestamp: new Date().toISOString()
            }
        },
        
        async mounted() {
            // Initialize database if db file is specified
            if (this.exercise.exercise_data.db) {
                await this.loadDatabase();
            }
        },
        
        methods: {
            async getGuidance(action: 'run_query' | 'ask_hint' | 'ask_question', details: { question?: string | null, error?: string | null } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    console.log(`Getting guidance for action: ${action}`);

                    // 1. Get CSRF token
                    const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                    if (!csrfTokenElement) {
                        console.error('CSRF token not found!');
                        this.queryError = 'Could not find CSRF token on page. Cannot contact server.';
                        return;
                    }
                    const csrfToken = csrfTokenElement.value;

                    // 2. Prepare payload
                    const payload = {
                        action: action,
                        code: this.userQuery,
                        query_result: this.queryResult ? JSON.stringify(this.queryResult, null, 2) : null,
                        question: details.question || null,
                        error_message: details.error || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString()
                    };

                    // 3. Make API call
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
                    console.log('Guidance received:', result);
                    this.guidance = result.guidance; // Store the guidance

                    // Add the user submission to the chat history
                    if (result.user_submission) {
                        this.chatMessages.push(result.user_submission);
                    }

                    // Add the assistant's response to the chat
                    if (result.guidance) {
                        let guidanceText = result.guidance;
                        if (guidanceText.includes('<exercise_completed>')) {
                            // Trigger confetti when exercise is completed
                            confetti({
                                particleCount: 200,
                                spread: 150,
                                origin: { y: 0.6 }
                            });
                            // Remove the tag from the message
                            guidanceText = guidanceText.replace('<exercise_completed>', '').trim();
                        }
                        this.chatMessages.push({ role: 'assistant', content: guidanceText });
                    }

                } catch (error) {
                    console.error('Failed to get guidance:', error);
                    this.queryError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString(); // Reset for the next interaction
                }
            },

            async loadDatabase() {
                try {
                    this.loadingState = 'db-loading';

                    // When integrating a class-based library like PGlite with Vue,
                    // it's crucial to prevent Vue from making the library's instance
                    // reactive. Vue's reactivity system wraps objects in Proxies,
                    // which can interfere with the internal private fields of complex
                    // classes, leading to "Cannot read from private field" errors.
                    // `markRaw` tells Vue to treat the PGlite instance as a raw,
                    // non-reactive object, preserving its internal integrity.
                    this.database = markRaw(await PGlite.create());

                    // Fetch and execute the SQL file from the asset endpoint
                    if (!assetUrl) {
                        throw new Error('Asset URL not provided in the template.');
                    }
                    const sql = await fetch(assetUrl).then(res => res.text());
                    
                    await this.database.exec(sql);
                    
                } catch (error) {
                    console.error('Error loading database:', error);
                    this.queryError = 'Failed to load database: ' + String(error);
                } finally {
                    this.loadingState = 'idle';
                }
            },
            
            async runQuery() {
                if (!this.database) {
                    this.queryError = 'Database not loaded yet. Please wait...';
                    return;
                }
                
                if (!this.userQuery.trim()) {
                    this.queryError = 'Please enter a query';
                    return;
                }
                
                try {
                    this.loadingState = 'querying';
                    this.queryError = null;
                    this.queryResult = null;
                    
                    const result = await this.database.query(this.userQuery);
                    
                    // Format result based on query type
                    if (result.rows && result.rows.length > 0) {
                        // SELECT query with results
                        this.queryResult = {
                            type: 'select',
                            columns: result.fields.map((field: any) => field.name),
                            rows: result.rows,
                            rowCount: result.rows.length
                        };
                    } else if (result.affectedRows !== undefined) {
                        // INSERT/UPDATE/DELETE query
                        this.queryResult = {
                            type: 'modification',
                            affectedRows: result.affectedRows,
                            message: `${result.affectedRows} row(s) affected`
                        };
                    } else {
                        // Other queries (CREATE, DROP, etc.)
                        this.queryResult = {
                            type: 'other',
                            message: 'Query executed successfully'
                        };
                    }
                    
                    // After successfully running the query, get guidance
                    await this.getGuidance('run_query');

                } catch (error) {
                    console.error('Query error:', error);
                    const errorMessage = 'SQL Error: ' + String(error);
                    this.queryError = errorMessage;

                    // When there's an error, also get guidance
                    await this.getGuidance('run_query', { error: errorMessage });
                }
            },

            giveHint() {
                this.getGuidance('ask_hint');
            },
            
            handleQuestion(question: string) {
                this.getGuidance('ask_question', { question: question });
            },

            getResultColumns(resultArray: Record<string, any>[] | undefined): string[] {
                if (!resultArray || resultArray.length === 0) return [];
                return Object.keys(resultArray[0]!);
            }
        },
        
        components: {
            'code-mirror-editor': CodeMirrorEditor,
            'chatbot-panel': ChatbotPanel
        }
    });
    
    const app = createApp(SqlExerciseApp);
    app.mount('#sql-exercise-app');
});