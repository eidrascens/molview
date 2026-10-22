import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outDir = path.join(root, 'web', 'dist');
await mkdir(outDir, { recursive: true });
await build({
  entryPoints: [path.join(root, 'web', 'src', 'viewer.ts')],
  outfile: path.join(outDir, 'viewer.js'),
  bundle: true,
  platform: 'browser',
  format: 'iife',
  target: ['es2022'],
  sourcemap: true,
  minify: false,
  logLevel: 'info',
});
await copyFile(path.join(root, 'web', 'index.html'), path.join(outDir, 'index.html'));
console.log(`Mol* frontend written to ${outDir}`);
