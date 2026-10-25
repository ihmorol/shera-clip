import { copyFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const output = fileURLToPath(new URL('./dist/', import.meta.url));
mkdirSync(output, {recursive:true});
for (const name of ['index.html','app.js','style.css','companion.zip']) {
  copyFileSync(new URL('./public/' + name, import.meta.url), new URL('./dist/' + name, import.meta.url));
}
