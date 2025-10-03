// This file is the entry point for Rollup to build the CodeMirror bundle.
// It imports the necessary CodeMirror modules and re-exports them so that
// the browser only needs a single bundle.

import { EditorView, keymap } from '@codemirror/view';
import { basicSetup } from 'codemirror';
import { EditorState, Compartment } from '@codemirror/state';
import { indentUnit, indentOnInput } from '@codemirror/language';
import { sql } from '@codemirror/lang-sql';
import { python as pythonLang } from '@codemirror/lang-python';
import { StreamLanguage } from '@codemirror/language';
import { scala as legacyScala } from '@codemirror/legacy-modes/mode/clike';
import { indentWithTab as indentWithTabCmd, indentMore as indentMoreCmd, indentLess as indentLessCmd } from '@codemirror/commands';
import { autocompletion, acceptCompletion, CompletionContext } from '@codemirror/autocomplete';
import { oneDark } from '@codemirror/theme-one-dark';

// SQL keywords for autocomplete
const SQL_KEYWORDS = [
    'SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 
    'ALTER', 'TABLE', 'INDEX', 'VIEW', 'DATABASE', 'JOIN', 'INNER', 
    'LEFT', 'RIGHT', 'OUTER', 'ON', 'AS', 'AND', 'OR', 'NOT', 'NULL', 'IS', 
    'IN', 'BETWEEN', 'LIKE', 'GROUP', 'BY', 'HAVING', 'ORDER', 'ASC', 'DESC', 
    'LIMIT', 'OFFSET', 'UNION', 'ALL', 'DISTINCT', 'CASE', 'THEN', 
    'ELSE', 'END', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'CAST', 'INTO', 'VALUES',
    'SET', 'PRIMARY', 'KEY', 'REFERENCES', 'DEFAULT', 'UNIQUE',
    'CHECK', 'CONSTRAINT', 'EXISTS', 'WITH', 'RECURSIVE'
];

// Custom SQL keyword-only autocomplete
export function sqlKeywordCompletion(context) {
    const word = context.matchBefore(/\w*/);
    if (!word || (word.from === word.to && !context.explicit)) return null;
    
    const options = SQL_KEYWORDS.map(keyword => ({
        label: keyword,
        type: 'keyword',
        apply: keyword
    }));
    
    return {
        from: word.from,
        options: options,
        filter: true
    };
}

// Re-export under the canonical names expected by the rest of the codebase.
export const python = pythonLang;
export const scala = () => StreamLanguage.define(legacyScala);
export const indentWithTab = indentWithTabCmd;
export const indentMore = indentMoreCmd;
export const indentLess = indentLessCmd;
export { indentUnit };
export { indentOnInput };
export { autocompletion, acceptCompletion, CompletionContext };
export { oneDark };
export { Compartment };

export {
  EditorView,
  keymap,
  basicSetup,
  EditorState,
  sql
}; 