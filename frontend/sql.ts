import { PGlite } from '@electric-sql/pglite';

// Declare global variables that are loaded via script tags in the HTML template
declare const CodeMirror: any;

// Extend the Window interface to declare Vue is available
declare global {
    interface Window {
        Vue: any;
    }
}

// Define the shape of our exercise data for type safety
interface Exercise {
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

// CodeMirror Editor Component - using any for Vue component typing
const CodeMirrorEditor: any = {
    props: {
        language: {
            type: String,
            default: 'text'
        },
        modelValue: {
            type: String,
            default: ''
        },
        placeholder: {
            type: String,
            default: '-- Write your code here'
        }
    },
    emits: ['update:modelValue', 'run-query'],
    template: `<div ref="editorContainer" class="code-editor"></div>`,
    
    data() {
        return {
            editor: null as any
        }
    },
    
    mounted() {
        const container = (this as any).$refs.editorContainer as HTMLDivElement;
        (this as any).editor = CodeMirror(container, {
            mode: (this as any).language,
            value: (this as any).modelValue,
            lineNumbers: true,
            theme: 'eclipse',
            indentUnit: 2,
            tabSize: 2,
            lineWrapping: true,
            extraKeys: {
                'Ctrl-Space': 'autocomplete',
                'Ctrl-Enter': () => {
                    (this as any).$emit('run-query');
                }
            }
        });
        
        (this as any).editor.on('change', (editor: any) => {
            (this as any).$emit('update:modelValue', editor.getValue());
        });
    },
    
    watch: {
        modelValue(newValue: string) {
            const editor = (this as any).editor;
            if (editor && editor.getValue() !== newValue) {
                editor.setValue(newValue);
            }
        }
    },
    
    beforeUnmount() {
        const editor = (this as any).editor;
        if (editor) {
            // Clean up the editor instance
            editor.getWrapperElement().remove();
            (this as any).editor = null;
        }
    }
};

document.addEventListener('DOMContentLoaded', function() {
    const { createApp, markRaw } = window.Vue;
    
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
    
    // Main Vue app - using any for component typing
    const app: any = createApp({
        delimiters: ['[[', ']]'],
        data() {
            return {
                exercise: exerciseData,
                userQuery: '',
                showHints: false,
                showExpectedResult: false,
                showCorrectAnswers: false,
                queryResult: null as any,
                queryError: null as string | null,
                isLoading: false,
                database: null as any,
                databaseLoaded: false
            }
        },
        
        async mounted() {
            // Initialize database if db file is specified
            if ((this as any).exercise.exercise_data.db) {
                await (this as any).loadDatabase();
            }
        },
        
        methods: {
            async loadDatabase() {
                try {
                    (this as any).isLoading = true;

                    // When integrating a class-based library like PGlite with Vue,
                    // it's crucial to prevent Vue from making the library's instance
                    // reactive. Vue's reactivity system wraps objects in Proxies,
                    // which can interfere with the internal private fields of complex
                    // classes, leading to "Cannot read from private field" errors.
                    // `markRaw` tells Vue to treat the PGlite instance as a raw,
                    // non-reactive object, preserving its internal integrity.
                    (this as any).database = markRaw(await PGlite.create());

                    // Fetch and execute the SQL file from the asset endpoint
                    if (!assetUrl) {
                        throw new Error('Asset URL not provided in the template.');
                    }
                    const sql = await fetch(assetUrl).then(res => res.text());
                    
                    await (this as any).database.exec(sql);
                    
                    (this as any).databaseLoaded = true;
                } catch (error) {
                    console.error('Error loading database:', error);
                    (this as any).queryError = 'Failed to load database: ' + String(error);
                } finally {
                    (this as any).isLoading = false;
                }
            },
            
            async runQuery() {
                if (!(this as any).database || !(this as any).databaseLoaded) {
                    (this as any).queryError = 'Database not loaded yet. Please wait...';
                    return;
                }
                
                if (!(this as any).userQuery.trim()) {
                    (this as any).queryError = 'Please enter a query';
                    return;
                }
                
                try {
                    (this as any).isLoading = true;
                    (this as any).queryError = null;
                    (this as any).queryResult = null;
                    
                    const result = await (this as any).database.query((this as any).userQuery);
                    
                    // Format result based on query type
                    if (result.rows && result.rows.length > 0) {
                        // SELECT query with results
                        (this as any).queryResult = {
                            type: 'select',
                            columns: result.fields.map((field: any) => field.name),
                            rows: result.rows,
                            rowCount: result.rows.length
                        };
                    } else if (result.affectedRows !== undefined) {
                        // INSERT/UPDATE/DELETE query
                        (this as any).queryResult = {
                            type: 'modification',
                            affectedRows: result.affectedRows,
                            message: `${result.affectedRows} row(s) affected`
                        };
                    } else {
                        // Other queries (CREATE, DROP, etc.)
                        (this as any).queryResult = {
                            type: 'other',
                            message: 'Query executed successfully'
                        };
                    }
                } catch (error) {
                    console.error('Query error:', error);
                    (this as any).queryError = 'SQL Error: ' + String(error);
                } finally {
                    (this as any).isLoading = false;
                }
            },
            
            clearQuery() {
                (this as any).userQuery = '';
                (this as any).queryResult = null;
                (this as any).queryError = null;
            },
            
            getResultColumns(resultArray: Record<string, any>[] | undefined): string[] {
                if (!resultArray || resultArray.length === 0) return [];
                return Object.keys(resultArray[0]!);
            }
        },
        
        components: {
            'code-mirror-editor': CodeMirrorEditor
        }
    });
    
    app.mount('#sql-exercise-app');
}); 