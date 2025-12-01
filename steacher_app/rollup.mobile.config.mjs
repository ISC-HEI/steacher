import { nodeResolve } from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import typescript from '@rollup/plugin-typescript';

export default {
  input: 'frontend/mobile_chat.ts',
  output: {
    file: 'static/js/dist/mobile_chat.bundle.js',
    format: 'iife',
    name: 'MobileChat',
    globals: {
      'vue': 'Vue',
      'marked': 'marked',
      'dompurify': 'DOMPurify',
      'katex': 'katex'
    }
  },
  external: ['vue', 'marked', 'dompurify', 'katex'],
  plugins: [
    typescript({
      tsconfig: './tsconfig.json',
      sourceMap: false,
      inlineSources: false
    }),
    nodeResolve(),
    commonjs()
  ]
};

