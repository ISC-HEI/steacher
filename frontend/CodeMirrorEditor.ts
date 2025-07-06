// Declare global variables that are loaded via script tags in the HTML template
declare const CodeMirror: any;

// CodeMirror Editor Component - using any for Vue component typing
export const CodeMirrorEditor: any = {
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
        const editor = CodeMirror(container, {
            mode: (this as any).language,
            value: (this as any).modelValue,
            placeholder: (this as any).placeholder,
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
        (this as any).editor = editor;

        editor.on('change', (editorInstance: any) => {
            const currentValue = editorInstance.getValue();
            (this as any).$emit('update:modelValue', currentValue);
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
            editor.getWrapperElement().remove();
            (this as any).editor = null;
        }
    }
}; 