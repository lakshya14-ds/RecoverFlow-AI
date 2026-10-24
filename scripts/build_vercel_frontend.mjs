import { cpSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const raw = process.env.RECOVERFLOW_BACKEND_URL;
if (!raw) {
  throw new Error('Set RECOVERFLOW_BACKEND_URL to the public HTTPS origin of the running FastAPI backend.');
}

const url = new URL(raw);
if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
  throw new Error('RECOVERFLOW_BACKEND_URL must be an HTTPS origin, such as https://api.example.com');
}

const output = resolve('dist');
rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
cpSync(resolve('frontend'), output, { recursive: true });
writeFileSync(resolve(output, 'config.js'),
  `window.RECOVERFLOW_BACKEND_ORIGIN = ${JSON.stringify(url.origin)};\n`);
console.log(`Built Vercel frontend for backend ${url.origin}`);
