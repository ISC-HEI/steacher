import { nodeResolve } from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';

export default {
  input: 'frontend/codemirror-entry.js',
  output: {
    file: 'static/js/dist/codemirror-bundle.js',
    format: 'es'
  },
  plugins: [
    nodeResolve(),
    commonjs()
  ]
}; 