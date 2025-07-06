import type { DefineComponent } from 'vue';

// Declare global variables that are loaded via script tags in the HTML template
declare const CodeMirror: any;

interface CodeMirrorEditorData {
    editor: any | null; // CodeMirror.Editor is not easily typed here
}

// CodeMirror Editor Component - using any for Vue component typing
export const CodeMirrorEditor = (window.Vue as typeof import('vue')).defineComponent({
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

    data(): CodeMirrorEditorData {
        return {
            editor: null,
        }
    },

    mounted() {
        this.$nextTick(() => {
            const container = this.$refs.editorContainer as HTMLDivElement;
            if (!container) return;

            const editor = CodeMirror(container, {
                mode: this.language,
                value: this.modelValue,
                placeholder: this.placeholder,
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
            this.editor = editor;

            editor.on('change', (editorInstance: any) => {
                const currentValue = editorInstance.getValue();
                this.$emit('update:modelValue', currentValue);
            });

            // Refresh the editor after the initial rendering to fix layout issues
            setTimeout(() => {
                editor.refresh();
            }, 10); // A small delay can help ensure rendering is complete
        });
    },

    watch: {
        modelValue(newValue: string) {
            const editor = this.editor;
            if (editor && editor.getValue() !== newValue) {
                editor.setValue(newValue);
            }
        }
    },

    beforeUnmount() {
        const editor = this.editor;
        if (editor) {
            editor.getWrapperElement().remove();
            this.editor = null;
        }
    }
}); 