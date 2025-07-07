// This file is for custom type declarations

declare module 'codemirror-bundle' {
    export * from 'codemirror';
    export * from '@codemirror/state';
    export * from '@codemirror/lang-sql';
    // Added for Python language support and extra commands/view utilities
    export * from '@codemirror/lang-python';
    export * from '@codemirror/view';
    export * from '@codemirror/commands';
}

declare module 'canvas-confetti';
declare module 'pyodide'; 