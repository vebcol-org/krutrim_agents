/// <reference types='vitest' />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dts from 'vite-plugin-dts';

// Library build — see libs/shared-types/vite.config.mts's comment for why
// `external` treats every bare specifier (echarts, lightweight-charts, react, ...)
// as external rather than bundled. `test` mirrors libs/extensions/vite.config.mts:
// this is a rendering library with real chart-data logic worth locking down,
// not just a build target.
export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/libs/agent-dashboard',
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
    name: 'agent-dashboard',
    watch: false,
    globals: true,
    environment: 'jsdom',
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
    reporters: ['default'],
    coverage: {
      reportsDirectory: '../../coverage/libs/agent-dashboard',
      provider: 'v8' as const,
    },
  },
}));
