// ESLint flat config (ESLint 9+).
import js from '@eslint/js';
import ts from 'typescript-eslint';
import reactPlugin from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import importPlugin from 'eslint-plugin-import';
import prettier from 'eslint-config-prettier';

export default ts.config(
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**', '*.config.js', '*.config.ts', 'src/test/**'] },

  js.configs.recommended,
  ...ts.configs.strict,
  ...ts.configs.stylistic,

  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { react: reactPlugin, 'react-hooks': reactHooks, import: importPlugin },
    languageOptions: {
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
      },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // React 17+ автоматический JSX runtime — импорт React не нужен
      'react/react-in-jsx-scope': 'off',
      'react/jsx-uses-react': 'off',
      'react/prop-types': 'off', // используем TypeScript

      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // unused vars с _ префиксом игнорируем
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],

      // warning-ратчет держит их суммой на нуле-в-росте (цель — 0)
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-non-null-assertion': 'warn',
      'no-console': ['warn', { allow: ['warn', 'error'] }],

      // Function-level limits
      'max-lines-per-function': ['warn', { max: 80, skipBlankLines: true, skipComments: true }],
      complexity: ['warn', 10],
      'max-depth': ['warn', 4],
      'max-params': ['warn', 5],

      'import/order': [
        'warn',
        { 'newlines-between': 'always', groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'] },
      ],
    },
  },

  // Prettier — ПОСЛЕДНИМ, чтобы отключить конфликтующие стилевые правила
  prettier,
);
