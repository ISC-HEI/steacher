// Declare global variables that are loaded via script tags in the HTML template
declare const CodeMirror: any;

// Extend the Window interface to declare Vue is available
interface Window {
    Vue: any;
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
    const { createApp } = window.Vue;
    
    // Get exercise data from JSON script tag
    const exerciseDataScript = document.getElementById('exercise-data');
    if (!exerciseDataScript) {
        console.error('Exercise data script tag not found!');
        return;
    }
    const exerciseData: Exercise = JSON.parse(exerciseDataScript.textContent || '{}');
    
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
                queryResult: null as string | null
            }
        },
        
        methods: {
            runQuery() {
                console.log('Running query:', (this as any).userQuery);
                (this as any).queryResult = 'Query execution will be implemented later...';
            },
            
            clearQuery() {
                (this as any).userQuery = '';
                (this as any).queryResult = null;
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