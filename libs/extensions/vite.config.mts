/// <reference types='vitest' />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dts from 'vite-plugin-dts';

// Library build — see libs/shared-types/vite.config.mts's comment for why
// `external` treats every bare specifier as external rather than bundled.
// `test` is the only project (of the newly-packaged libs) with one: this is
// where `ExtensionSelfCheck`'s drift-detection logic — actual user-visible
// behavior worth locking down — gets exercised, not just built.
export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/libs/extensions',
  plugins: [react(), dts({ entryRoot: 'src', tsconfigPath: 'tsconfig.lib.json' })],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    lib: {
      entry: 'src/index.ts',
      formats: ['es'],
      fileName: 'index',
    },
    rollupOptions: {
      external: (id: string) => !/^[./]/.test(id),
    },
  },
  test: {
    name: 'extensions',
    watch: false,
    globals: true,
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    reporters: ['default'],
    coverage: {
      reportsDirectory: '../../coverage/libs/extensions',
      provider: 'v8' as const,
    },
  },
}));
