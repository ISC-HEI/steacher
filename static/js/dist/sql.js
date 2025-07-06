import { PGlite } from '@electric-sql/pglite';
// CodeMirror Editor Component - using any for Vue component typing
const CodeMirrorEditor = {
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
            editor: null
        };
    },
    mounted() {
        const container = this.$refs.editorContainer;
        this.editor = CodeMirror(container, {
            mode: this.language,
            value: this.modelValue,
            lineNumbers: true,
            theme: 'eclipse',
            indentUnit: 2,
            tabSize: 2,
            lineWrapping: true,
            extraKeys: {
                'Ctrl-Space': 'autocomplete',
                'Ctrl-Enter': () => {
                    this.$emit('run-query');
                }
            }
        });
        this.editor.on('change', (editor) => {
            this.$emit('update:modelValue', editor.getValue());
        });
    },
    watch: {
        modelValue(newValue) {
            const editor = this.editor;
            if (editor && editor.getValue() !== newValue) {
                editor.setValue(newValue);
            }
        }
    },
    beforeUnmount() {
        const editor = this.editor;
        if (editor) {
            // Clean up the editor instance
            editor.getWrapperElement().remove();
            this.editor = null;
        }
    }
};
document.addEventListener('DOMContentLoaded', function () {
    const { createApp, markRaw } = window.Vue;
    // Get exercise data from JSON script tag
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('sql-exercise-app');
    if (!exerciseDataScript || !appElement) {
        console.error('Required script tags or app element not found!');
        return;
    }
    const exerciseData = JSON.parse(exerciseDataScript.textContent || '{}');
    const staticPrefix = appElement.dataset.staticPrefix || '/static/';
    const assetUrl = appElement.dataset.assetUrl || '';
    // Main Vue app - using any for component typing
    const app = createApp({
        delimiters: ['[[', ']]'],
        data() {
            return {
                exercise: exerciseData,
                userQuery: '',
                showHints: false,
                showExpectedResult: false,
                showCorrectAnswers: false,
                queryResult: null,
                queryError: null,
                loadingState: 'idle', // 'idle', 'db-loading', 'querying'
                database: null
            };
        },
        async mounted() {
            // Initialize database if db file is specified
            if (this.exercise.exercise_data.db) {
                await this.loadDatabase();
            }
        },
        methods: {
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
                }
                catch (error) {
                    console.error('Error loading database:', error);
                    this.queryError = 'Failed to load database: ' + String(error);
                }
                finally {
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
                            columns: result.fields.map((field) => field.name),
                            rows: result.rows,
                            rowCount: result.rows.length
                        };
                    }
                    else if (result.affectedRows !== undefined) {
                        // INSERT/UPDATE/DELETE query
                        this.queryResult = {
                            type: 'modification',
                            affectedRows: result.affectedRows,
                            message: `${result.affectedRows} row(s) affected`
                        };
                    }
                    else {
                        // Other queries (CREATE, DROP, etc.)
                        this.queryResult = {
                            type: 'other',
                            message: 'Query executed successfully'
                        };
                    }
                }
                catch (error) {
                    console.error('Query error:', error);
                    this.queryError = 'SQL Error: ' + String(error);
                }
                finally {
                    this.loadingState = 'idle';
                }
            },
            clearQuery() {
                this.userQuery = '';
                this.queryResult = null;
                this.queryError = null;
            },
            getResultColumns(resultArray) {
                if (!resultArray || resultArray.length === 0)
                    return [];
                return Object.keys(resultArray[0]);
            }
        },
        components: {
            'code-mirror-editor': CodeMirrorEditor
        }
    });
    app.mount('#sql-exercise-app');
});
