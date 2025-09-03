import { defineComponent } from 'vue';
import { EditorView, basicSetup, EditorState, sql, python, keymap, indentWithTab, indentUnit, autocompletion, acceptCompletion } from 'codemirror-bundle';
import type { ViewUpdate } from '@codemirror/view';

interface CodeMirrorEditorData {
    editor: EditorView | null;
}

// CodeMirror Editor Component
export const CodeMirrorEditor = defineComponent({
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

            // Get language extension based on prop
            const languageExtension = this.getLanguageExtension();

            // Create editor state
            const state = EditorState.create({
                doc: this.modelValue,
                extensions: [
                    basicSetup,
                    autocompletion(),
                    keymap.of([
                        // Tab accepts completion when the popup is open; otherwise indent
                        {
                            key: 'Tab',
                            run: (view: EditorView) => (acceptCompletion as any)(view) || (indentWithTab as any)(view),
                        },
                        indentWithTab,
                    ]),
                    languageExtension,
                    // Use 4 spaces indentation for Python
                    ...(this.language === 'python' ? [indentUnit.of('    ')] : []),
                    EditorView.updateListener.of((update: ViewUpdate) => {
                        if (update.docChanged) {
                            const newValue = update.state.doc.toString();
                            this.$emit('update:modelValue', newValue);
                        }
                    }),
                    EditorView.domEventHandlers({
                        keydown: (event: KeyboardEvent, view: EditorView) => {
                            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                                this.$emit('run-query');
                                return true;
                            }
                            return false;
                        }
                    }),
                    EditorView.theme({
                        "&": {
                            maxHeight: "600px", // Approx. 30 lines
                            fontSize: "14px"
                        },
                        ".cm-scroller": {
                            overflow: "auto"
                        },
                        ".cm-content, .cm-gutter": {
                            minHeight: "240px" // Approx. 10 lines
                        },
                        ".cm-focused": {
                            outline: "none"
                        }
                    })
                ]
            });

            // Create editor view
            this.editor = new EditorView({
                state,
                parent: container
            });
        });
    },

    methods: {
        getLanguageExtension() {
            switch (this.language) {
                case 'sql':
                    return sql();
                case 'python':
                    return python();
                default:
                    return [];
            }
        }
    },

    watch: {
        modelValue(newValue: string) {
            const editor = this.editor;
            if (editor && editor.state.doc.toString() !== newValue) {
                editor.dispatch({
                    changes: { from: 0, to: editor.state.doc.length, insert: newValue }
                });
            }
        }
    },

    beforeUnmount() {
        if (this.editor) {
            this.editor.destroy();
            this.editor = null;
        }
    }
}); 