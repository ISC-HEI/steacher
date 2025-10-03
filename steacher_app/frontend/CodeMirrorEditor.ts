import { defineComponent } from 'vue';
import { EditorView, basicSetup, EditorState, sql, python, scala, keymap, indentUnit, autocompletion, acceptCompletion, indentMore, indentLess, indentOnInput, oneDark, Compartment, sqlKeywordCompletion } from 'codemirror-bundle';
import type { ViewUpdate } from '@codemirror/view';

interface CodeMirrorEditorData {
    editor: EditorView | null;
    themeCompartment: any;
    darkModeMedia: MediaQueryList | null;
}

// CodeMirror Editor Component
export const CodeMirrorEditor = defineComponent({
    props: {
        // like sql, python, scala
        language: {
            type: String,
            default: 'text'
        },
        // where the code that the user is writing is stored
        modelValue: {
            type: String,
            default: ''
        },
        // what the user sees when the editor is empty
        placeholder: {
            type: String,
            default: '-- Write your code here'
        },
        // where the code that the user is writing is stored, so that if the user refreshes the page, the code is not lost
        persistenceKey: {
            type: String,
            default: null
        }
    },
    emits: ['update:modelValue', 'run-query'],
    template: `<div ref="editorContainer" class="code-editor"></div>`,

    data(): CodeMirrorEditorData {
        return {
            editor: null,
            themeCompartment: null,
            darkModeMedia: null,
        }
    },

    mounted() {
        this.$nextTick(() => {
            const container = this.$refs.editorContainer as HTMLDivElement;
            if (!container) return;

            let initialDoc = this.modelValue;
            // If a persistenceKey is provided, attempt to restore the editor's
            // content from localStorage. This allows users to refresh the page
            // or navigate away without losing their work.
            if (this.persistenceKey) {
                try {
                    const savedContent = localStorage.getItem(this.persistenceKey);
                    // Prefer locally saved content when available and different from the server value.
                    if (savedContent && savedContent !== initialDoc) {
                        initialDoc = savedContent;
                        this.$emit('update:modelValue', savedContent);
                    }
                } catch (e) {
                    console.warn('Error restoring editor content from localStorage', e);
                    // Ignore storage errors (e.g., private mode)
                }
            }

            // Get language extension based on prop
            const languageExtension = this.getLanguageExtension();

            // Prepare theme compartment for dynamic dark-mode switching
            this.themeCompartment = new Compartment();
            const isDarkMode = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)').matches : false;

            // Create editor state
            const state = EditorState.create({
                doc: initialDoc,
                extensions: [
                    basicSetup,
                    keymap.of([
                        // Tab: accept completion if available, otherwise indent
                        {
                            key: 'Tab',
                            run: (view: EditorView) => {
                                // Try to accept completion first
                                if (acceptCompletion(view)) {
                                    return true;
                                }
                                // If no completion, indent
                                return indentMore(view);
                            }
                        },
                        {key: 'Shift-Tab', run: (indentLess as any) },
                    ]),
                    languageExtension,
                    // Use a neutral light theme when not in dark mode (avoid passing [])
                    this.themeCompartment.of(isDarkMode ? oneDark : EditorView.theme({}, { dark: false })),
                    indentOnInput(),
                    // Use 4 spaces indentation for Python
                    ...(this.language === 'python' ? [indentUnit.of('    ')] : []),
                    // Use custom SQL keyword-only autocomplete for SQL
                    ...(this.language === 'sql' ? [autocompletion({ override: [sqlKeywordCompletion] })] : []),
                    // Save content to localStorage on every keystroke
                    EditorView.updateListener.of((update: ViewUpdate) => {
                        if (update.docChanged) {
                            const newValue = update.state.doc.toString();
                            this.$emit('update:modelValue', newValue);
                            if (this.persistenceKey) {
                                try {
                                    localStorage.setItem(this.persistenceKey, newValue);
                                } catch (e) {
                                    // Ignore storage errors
                                    console.warn('Error saving editor content to localStorage', e);
                                }
                            }
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
                            fontSize: "16px"
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

            // React to OS dark mode changes
            if (typeof window !== 'undefined' && window.matchMedia) {
                this.darkModeMedia = window.matchMedia('(prefers-color-scheme: dark)');
                const handler = (e: MediaQueryListEvent) => {
                    if (!this.editor) return;
                    this.editor.dispatch({
                        effects: this.themeCompartment.reconfigure(e.matches ? oneDark : EditorView.theme({}, { dark: false }))
                    });
                };
                // Some browsers support addEventListener; others use addListener
                if (typeof this.darkModeMedia.addEventListener === 'function') {
                    this.darkModeMedia.addEventListener('change', handler);
                } else if (typeof (this.darkModeMedia as any).addListener === 'function') {
                    (this.darkModeMedia as any).addListener(handler);
                }
                // Store handler reference for cleanup
                (this as any)._darkModeHandler = handler;
            }
        });
    },

    beforeUnmount() {
        // Clean up dark mode listener
        if (this.darkModeMedia && (this as any)._darkModeHandler) {
            const handler = (this as any)._darkModeHandler;
            if (typeof this.darkModeMedia.removeEventListener === 'function') {
                this.darkModeMedia.removeEventListener('change', handler);
            } else if (typeof (this.darkModeMedia as any).removeListener === 'function') {
                (this.darkModeMedia as any).removeListener(handler);
            }
        }
    },

    methods: {
        getLanguageExtension() {
            switch (this.language) {
                case 'sql':
                    return sql();
                case 'python':
                    return python();
                case 'scala':
                    return scala();
                default:
                    return [];
            }
        }
    },

    watch: {
        modelValue(newValue: string) {
            if (this.persistenceKey) {
                localStorage.setItem(this.persistenceKey, newValue);
            }
            const editor = this.editor;
            if (editor && editor.state.doc.toString() !== newValue) {
                editor.dispatch({
                    changes: { from: 0, to: editor.state.doc.length, insert: newValue }
                });
            }
        }
    }
}); 