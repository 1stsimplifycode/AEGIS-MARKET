import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { FlatCompat } from '@eslint/eslintrc';

/**
 * ESLint flat config.
 *
 * `next lint` is deprecated and removed in Next 16, so the project uses the ESLint CLI
 * directly. `FlatCompat` bridges the still-eslintrc-shaped `eslint-config-next` presets
 * into flat config, which is what the Next migration guide recommends until that package
 * ships a native flat export.
 */
const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url)),
});

const config = [
  {
    ignores: [
      '.next/**',
      // Anything that builds into its own directory so it never interleaves with `.next`
      // — the browser check, the capability audit, an ad-hoc reproduction. All generated,
      // none of it source, and a pattern rather than a list nobody remembers to extend.
      '.next-*/**',
      'node_modules/**',
      '.venv/**',
      'research/**',
      'scripts/**',
      'tests/**',
      'research_artifacts/**',
      'paper_package/**',
      'data/**',
      'next-env.d.ts',
    ],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      // The research bundles are deliberately loosely typed at the boundary: their shape
      // is defined by the Python exporter, and asserting a precise type here would be a
      // claim the TypeScript side cannot verify. The typed accessors in lib/data.ts are
      // where the shape is actually pinned down.
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
];

export default config;
