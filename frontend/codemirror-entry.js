// This file is the entry point for Rollup to build the CodeMirror bundle.
// It imports all the necessary CodeMirror modules.

import { EditorView, basicSetup } from 'codemirror';
import { EditorState } from '@codemirror/state';
import { sql } from '@codemirror/lang-sql';

// Export everything from a single point
export {
    EditorView,
    basicSetup,
    EditorState,
    sql
}; 