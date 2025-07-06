// CodeMirror Editor Component
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
    emits: ['update:modelValue'],
    template: `<div ref="editorContainer" class="code-editor"></div>`,
    
    mounted() {
        // Initialize CodeMirror
        this.editor = CodeMirror(this.$refs.editorContainer, {
            mode: this.language,
            value: this.modelValue,
            lineNumbers: true,
            theme: 'default',
            indentUnit: 2,
            tabSize: 2,
            lineWrapping: true,
            placeholder: this.placeholder,
            extraKeys: {
                'Ctrl-Space': 'autocomplete', // LATER autocomplete not working
                'Ctrl-Enter': () => {
                    // Emit a run query event
                    this.$emit('run-query');
                }
            }
        });
        
        // Handle changes
        this.editor.on('change', (editor) => {
            this.$emit('update:modelValue', editor.getValue());
        });
    },
    
    watch: {
        modelValue(newValue) {
            if (this.editor && this.editor.getValue() !== newValue) {
                this.editor.setValue(newValue);
            }
        }
    },
    
    beforeUnmount() {
        if (this.editor) {
            this.editor.toTextArea();
        }
    }
};

document.addEventListener('DOMContentLoaded', function() {
    const { createApp } = Vue;
    
    // Get exercise data from JSON script tag
    const exerciseDataScript = document.getElementById('exercise-data');
    const exerciseData = JSON.parse(exerciseDataScript.textContent);
    
    createApp({
        delimiters: ['[[', ']]'],  // Use [[ ]] instead of {{ }} to avoid Django conflicts
        data() {
            return {
                exercise: exerciseData,
                userQuery: '',
                showHints: false,
                showExpectedResult: false,
                showCorrectAnswers: false,
                queryResult: null
            }
        },
        
        methods: {
            runQuery() {
                // Placeholder for query execution
                console.log('Running query:', this.userQuery);
                this.queryResult = 'Query execution will be implemented later...';
            },
            
            clearQuery() {
                this.userQuery = '';
                this.queryResult = null;
            },
            
            getResultColumns(resultArray) {
                if (!resultArray || resultArray.length === 0) return [];
                return Object.keys(resultArray[0]);
            }
        },
        
        components: {
            'code-mirror-editor': CodeMirrorEditor
        }
    }).mount('#sql-exercise-app');
}); 