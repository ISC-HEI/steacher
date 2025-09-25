// This file is for custom type declarations

declare module 'codemirror-bundle' {
    export * from 'codemirror';
    export * from '@codemirror/state';
    export * from '@codemirror/lang-sql';
    export { python } from '@codemirror/lang-python';
    export { EditorView, keymap } from '@codemirror/view';
    export { indentWithTab, indentMore, indentLess } from '@codemirror/commands';
    export { autocompletion, acceptCompletion, CompletionContext } from '@codemirror/autocomplete';
    export { indentUnit, indentOnInput, StreamLanguage } from '@codemirror/language';
    export { oneDark } from '@codemirror/theme-one-dark';
    // Custom re-export provided by our bundle for Scala legacy mode
    export function scala(): any;
}

declare module 'canvas-confetti';
declare module 'pyodide'; 