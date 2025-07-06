// CodeMirror Editor Component - using any for Vue component typing
export const CodeMirrorEditor = {
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
        editor.on('change', (editorInstance) => {
            const currentValue = editorInstance.getValue();
            this.$emit('update:modelValue', currentValue);
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
            editor.getWrapperElement().remove();
            this.editor = null;
        }
    }
};
