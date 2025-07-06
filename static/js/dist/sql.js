"use strict";
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
    const { createApp } = window.Vue;
    // Get exercise data from JSON script tag
    const exerciseDataScript = document.getElementById('exercise-data');
    if (!exerciseDataScript) {
        console.error('Exercise data script tag not found!');
        return;
    }
    const exerciseData = JSON.parse(exerciseDataScript.textContent || '{}');
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
                queryResult: null
            };
        },
        methods: {
            runQuery() {
                console.log('Running query:', this.userQuery);
                this.queryResult = 'Query execution will be implemented later...';
            },
            clearQuery() {
                this.userQuery = '';
                this.queryResult = null;
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
