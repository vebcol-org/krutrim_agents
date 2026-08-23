import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dts from 'vite-plugin-dts';

// Library build — see libs/shared-types/vite.config.mts's comment for why
// `external` treats every bare specifier as external rather than bundled.
// No Tailwind plugin here: `theme.css` ships as raw, unprocessed source (see
// package.json's `exports["./theme.css"]`) — Tailwind compilation is always
// the *consuming app's* job, never done inside this library build.
export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/libs/ui',
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
}));
