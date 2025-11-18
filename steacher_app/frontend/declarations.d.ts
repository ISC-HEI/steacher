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
    // Custom SQL keyword-only autocomplete
    export function sqlKeywordCompletion(context: any): any;
}

declare module 'canvas-confetti';
declare module 'pyodide';

declare module 'katex' {
    export interface KatexOptions {
        displayMode?: boolean;
        throwOnError?: boolean;
        errorColor?: string;
        macros?: any;
        colorIsTextColor?: boolean;
        strict?: boolean | string;
        trust?: boolean | ((context: any) => boolean);
        maxSize?: number;
        maxExpand?: number;
        globalGroup?: boolean;
    }
    
    export function renderToString(tex: string, options?: KatexOptions): string;
    export function render(tex: string, element: HTMLElement, options?: KatexOptions): void;
} 