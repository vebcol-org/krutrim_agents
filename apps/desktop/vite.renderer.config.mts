import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { nxViteTsPaths } from '@nx/vite/plugins/nx-tsconfig-paths.plugin';

export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/apps/desktop-renderer',
  base: './',
  server: {
    port: 4300,
    host: 'localhost',
  },
  resolve: {
    alias: {
      '@ui-theme': new URL('../../libs/ui/src/theme.css', import.meta.url).pathname,
    },
  },
  plugins: [react(), tailwindcss(), nxViteTsPaths()],
  build: {
    outDir: '../../dist/apps/desktop/renderer',
    emptyOutDir: true,
    reportCompressedSize: true,
  },
}));
