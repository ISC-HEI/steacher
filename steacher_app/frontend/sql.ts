import { PGlite } from '@electric-sql/pglite';
import { csrfFetch, getCsrfToken } from './utils.js';
import { ChatbotPanel } from './ChatbotPanel.js';
import { CodeMirrorEditor } from './CodeMirrorEditor.js';
import { createApp, markRaw, defineComponent } from 'vue';
import confetti from 'canvas-confetti';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import type { Exercise } from './utils.js';

// Define the shape for the query result for type safety
interface QueryResult {
    type: 'select' | 'modification' | 'other';
    columns?: string[];
    rows?: Record<string, any>[];
    rowCount?: number;
    affectedRows?: number;
    message?: string;
}

interface TableColumn {
    column_name: string;
    data_type: string;
}

interface DatabaseSchema {
    [tableName: string]: TableColumn[];
}

interface ForeignKeyInfo {
    constraint_name: string;
    column_name: string;
    referenced_table: string;
    referenced_column: string;
}

interface SqlDataContext {
    exercise: Exercise;
    userQuery: string;
    showHints: boolean;
    showExpectedResult: boolean;
    showCorrectAnswers: boolean;
    queryResult: QueryResult | null;
    queryError: string | null;
    loadingState: 'idle' | 'engine-loading' | 'querying' | 'getting-guidance';
    database: any | null; // PGlite instance
    databaseSchema: DatabaseSchema | null;
    schemaError: string | null;
    guidance: string | null;
    start_timestamp: string;
    foreignKeysByTable?: Record<string, ForeignKeyInfo[]>;
    isPreview?: boolean;
    previewMeta?: { tableName: string; limit: number; maybeMore: boolean } | null;
    solutionUnlocked: boolean;
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
                userQuery: lastUserCode || (exerciseData.exercise_data && exerciseData.exercise_data.answer_template) || '', // Initialize with last saved code or template
                showHints: false,
                showExpectedResult: false,
                showCorrectAnswers: false,
                queryResult: null,
                queryError: null as string | null,
                loadingState: 'idle', // 'idle', 'db-loading', 'querying', 'getting-guidance'
                database: null,
                databaseSchema: null,
                schemaError: null,
                guidance: null,
                start_timestamp: new Date().toISOString(),
                foreignKeysByTable: {},
                isPreview: false,
                previewMeta: null,
                solutionUnlocked: false
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

            // Initialize database
            await this.loadDatabase();
        },
        
        methods: {
            renderMarkdown(this: any, content: string) {
                if (!content) return '';
                return DOMPurify.sanitize(marked.parse(content) as string);
            },
            async viewTableData(tableName: string) {
                if (!this.database) {
                    this.queryError = 'Database not loaded yet. Please wait...';
                    return;
                }
                try {
                    this.loadingState = 'querying';
                    this.queryError = null;
                    this.isPreview = true;
                    const limit = 50;
                    const sql = `SELECT * FROM "${tableName}" LIMIT ${limit};`;
                    const result = await this.database.query(sql);
                    if (result.rows && result.rows.length >= 0) {
                        this.queryResult = {
                            type: 'select',
                            columns: result.fields.map((field: any) => field.name),
                            rows: result.rows,
                            rowCount: result.rows.length
                        };
                        this.previewMeta = { tableName, limit, maybeMore: result.rows.length === limit };
                    } else {
                        this.queryResult = {
                            type: 'other',
                            message: 'No rows'
                        };
                        this.previewMeta = { tableName, limit, maybeMore: false };
                    }
                } catch (error) {
                    console.error('Preview query error:', error);
                    this.queryError = 'SQL Error: ' + String(error);
                } finally {
                    this.loadingState = 'idle';
                }
            },
            async getGuidance(action: 'run_submission' | 'ask_hint' | 'ask_question', details: { question?: string | null, error?: string | null } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    const csrfToken = getCsrfToken();

                    // 2. Prepare payload
                    const payload = {
                        action: action,
                        code: this.userQuery,
                        query_result: this.queryResult ? JSON.stringify(this.queryResult, null, 2) : null,
                        question: details.question || null,
                        error_message: details.error || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString(),
                        database_schema: this.databaseSchema,
                        foreign_keys: this.foreignKeysByTable,
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
                    this.guidance = result.guidance; // Store the guidance

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
                        const assistantMessage: any = { role: 'assistant', content: guidanceText };
                        if (result.assistant_trace_id) assistantMessage.trace_id = result.assistant_trace_id;
                        chatbotPanel.displayMessage(assistantMessage);
                    }

                } catch (error) {
                    console.error('Failed to get guidance:', error);
                    this.queryError = `Error communicating with the server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString(); // Reset for the next interaction
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

            async loadDatabase() {
                try {
                    this.loadingState = 'engine-loading';

                    // When integrating a class-based library like PGlite with Vue,
                    // it's crucial to prevent Vue from making the library's instance
                    // reactive. Vue's reactivity system wraps objects in Proxies,
                    // which can interfere with the internal private fields of complex
                    // classes, leading to "Cannot read from private field" errors.
                    // `markRaw` tells Vue to treat the PGlite instance as a raw,
                    // non-reactive object, preserving its internal integrity.
                    this.database = markRaw(await PGlite.create());

                    // If a database file is provided, fetch and execute it. Else, use the default database.
                    if (this.exercise.exercise_data.db) {
                        // Fetch and execute the SQL file from the asset endpoint
                        if (!assetUrl) {
                            throw new Error('Asset URL not provided in the template.');
                        }
                        const response = await fetch(assetUrl);
                        if (!response.ok) {
                            if (response.status === 404) {
                                throw new Error('Database file not found (404). This exercise might be misconfigured.');
                            }
                            throw new Error(`Failed to load database file (${response.status} ${response.statusText}).`);
                        }
                        const sql = await response.text();
                        await this.database.exec(sql);
                    }
                    
                    await this.loadSchema();
                    
                } catch (error) {
                    console.error('Error loading database:', error);
                    const message = 'Failed to load database: ' + String(error);
                    // Surface the error in both panels so it is clearly visible
                    this.schemaError = message;
                    this.queryError = message;
                } finally {
                    this.loadingState = 'idle';
                }
            },
            
            async loadSchema() {
                if (!this.database) {
                    this.schemaError = "Database not available to load schema.";
                    return;
                }
                try {
                    // Indicate schema is being loaded for the left panel
                    this.loadingState = 'db-loading' as any;
                    const tablesResult = await this.database.query(`
                        SELECT tablename 
                        FROM pg_tables 
                        WHERE schemaname = 'public'
                        ORDER BY tablename
                    `);
                    const tables: string[] = tablesResult.rows.map((row: any) => row.tablename);

                    const schema: DatabaseSchema = {};
                    for (const tableName of tables) {
                        const columnsResult = await this.database.query(
                           `SELECT column_name, data_type 
                            FROM information_schema.columns 
                            WHERE table_name = $1
                            ORDER BY ordinal_position;
                        `, [tableName]);
                        schema[tableName] = columnsResult.rows;
                    }
                    this.databaseSchema = schema;

                    // Load foreign keys after columns are ready
                    await this.loadForeignKeys();

                } catch (error) {
                    console.error('Error loading schema:', error);
                    this.schemaError = 'Failed to load database schema: ' + String(error);
                } finally {
                    // Schema load complete
                    this.loadingState = 'idle';
                }
            },

            async loadForeignKeys() {
                if (!this.database) return;
                try {
                    const fkResult = await this.database.query(`
                        SELECT
                          tc.table_name,
                          kcu.column_name,
                          ccu.table_name AS referenced_table,
                          ccu.column_name AS referenced_column,
                          tc.constraint_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                          ON tc.constraint_name = kcu.constraint_name
                          AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage ccu
                          ON ccu.constraint_name = tc.constraint_name
                          AND ccu.table_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                          AND tc.table_schema = 'public'
                        ORDER BY tc.table_name, kcu.ordinal_position;
                    `);

                    const mapping: Record<string, ForeignKeyInfo[]> = {};
                    for (const row of fkResult.rows as any[]) {
                        const tableName: string = row.table_name;
                        if (!mapping[tableName]) mapping[tableName] = [];
                        mapping[tableName].push({
                            constraint_name: row.constraint_name,
                            column_name: row.column_name,
                            referenced_table: row.referenced_table,
                            referenced_column: row.referenced_column
                        });
                    }
                    this.foreignKeysByTable = mapping;
                } catch (error) {
                    console.warn('Failed to load foreign keys:', error);
                    // Non-fatal; skip FK display if query fails
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
                    if (result && Array.isArray(result.rows) && result.fields) {
                        // SELECT query (even if zero rows)
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
                    
                    // Manual run clears preview flag
                    this.isPreview = false;
                    this.previewMeta = null;

                    // If the query may have changed the schema, refresh the schema explorer
                    if (this.isSchemaChangingQuery(this.userQuery)) {
                        await this.loadSchema();
                    }

                } catch (error) {
                    console.log('Query error (caused by student\'s own syntax error):', error);
                    const errorMessage = 'SQL Error: ' + String(error);
                    this.queryError = errorMessage;
                } finally {
                    this.loadingState = 'idle';
                }
            },

            async submitQuery() {
                // First run the query to get results
                await this.runQuery();

                // Get AI guidance whether successful or not
                if (this.queryError) {
                    await this.getGuidance('run_submission', { error: this.queryError });
                } else {
                    await this.getGuidance('run_submission');
                }
            },

            giveHint() {
                this.getGuidance('ask_hint', { error: this.queryError });
            },
            
            handleQuestion(question: string) {
                this.getGuidance('ask_question', { question: question, error: this.queryError });
            },

            getResultColumns(resultArray: Record<string, any>[] | undefined): string[] {
                if (!resultArray || resultArray.length === 0) return [];
                return Object.keys(resultArray[0]!);
            },

            isSchemaChangingQuery(query: string): boolean {
                if (!query) return false;
                const q = query.toLowerCase();
                // Intentionally simple; false positives are acceptable
                return q.includes('create ') || q.includes('alter ') || q.includes('drop ');
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