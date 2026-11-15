import {build} from 'esbuild';
import {rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root=fileURLToPath(new URL('../',import.meta.url));
const output=path.join(root,'public/bundle');
// Diretório reservado aos arquivos gerados; não remove HTML, ícones ou artes.
await rm(output,{recursive:true,force:true});
const result=await build({
  absWorkingDir:root,entryPoints:['src/app.js'],bundle:true,splitting:true,
  format:'esm',platform:'browser',target:'es2020',charset:'utf8',minify:true,
  outdir:'public/bundle',chunkNames:'chunks/[name]-[hash]',metafile:true,
});
console.log(JSON.stringify({outputs:Object.fromEntries(Object.entries(result.metafile.outputs)
  .map(([name,info])=>[name,{bytes:info.bytes,imports:info.imports}]))},null,2));
