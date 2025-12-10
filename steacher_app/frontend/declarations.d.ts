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

// Web Speech API types
interface SpeechRecognitionEvent extends Event {
    resultIndex: number;
    results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
    length: number;
    item(index: number): SpeechRecognitionResult;
    [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
    length: number;
    item(index: number): SpeechRecognitionAlternative;
    [index: number]: SpeechRecognitionAlternative;
    isFinal: boolean;
}

interface SpeechRecognitionAlternative {
    transcript: string;
    confidence: number;
}

interface SpeechRecognitionErrorEvent extends Event {
    error: string;
    message: string;
}

interface SpeechRecognition extends EventTarget {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    maxAlternatives: number;
    
    start(): void;
    stop(): void;
    abort(): void;
    
    onstart: ((this: SpeechRecognition, ev: Event) => any) | null;
    onend: ((this: SpeechRecognition, ev: Event) => any) | null;
    onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => any) | null;
    onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => any) | null;
}

declare var SpeechRecognition: {
    prototype: SpeechRecognition;
    new(): SpeechRecognition;
};

declare var webkitSpeechRecognition: {
    prototype: SpeechRecognition;
    new(): SpeechRecognition;
}; 