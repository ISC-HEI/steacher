// This file is the entry point for Rollup to build the CodeMirror bundle.
// It imports the necessary CodeMirror modules and re-exports them so that
// the browser only needs a single bundle.

import { EditorView, keymap } from '@codemirror/view';
import { basicSetup } from 'codemirror';
import { EditorState } from '@codemirror/state';
import { indentUnit } from '@codemirror/language';
import { sql } from '@codemirror/lang-sql';
import { python as pythonLang } from '@codemirror/lang-python';
import { indentWithTab as indentWithTabCmd } from '@codemirror/commands';
import { autocompletion, acceptCompletion, CompletionContext } from '@codemirror/autocomplete';

// Re-export under the canonical names expected by the rest of the codebase.
export const python = pythonLang;
export const indentWithTab = indentWithTabCmd;
export { indentUnit };
export { autocompletion, acceptCompletion, CompletionContext };

export {
  EditorView,
  keymap,
  basicSetup,
  EditorState,
  sql
}; 