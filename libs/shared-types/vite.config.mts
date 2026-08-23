import { defineConfig } from 'vite';
import dts from 'vite-plugin-dts';

// Library build (produces an installable `dist/` for `package.json`'s
// main/module/types) — distinct from an *app* build (apps/web/apps/desktop),
// which bundles everything for the browser. `external` treats every bare
// specifier (anything not starting with `.` or `/`) as external rather than
// bundled — that's every npm package this lib imports plus every sibling
// `@krutrim_agent/*` package, left as real `import` statements for the
// consumer's own node_modules/bundler to resolve (see each package's own
// `dependencies`/`peerDependencies`), never inlined into this lib's own bundle.
export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/libs/shared-types',
  plugins: [dts({ entryRoot: 'src', tsconfigPath: 'tsconfig.lib.json' })],
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
