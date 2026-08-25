import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettierConfig from 'eslint-config-prettier';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', '*.html', 'scripts/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.ts'],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // race-page.ts compiles to a classic script loaded before each page's
      // own inline <script>; its top-level functions are consumed from that
      // global scope, not from this file, so they read as unused here.
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
  {
    files: ['test/**/*.ts', '*.config.mts', '*.config.mjs'],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
  prettierConfig,
);
