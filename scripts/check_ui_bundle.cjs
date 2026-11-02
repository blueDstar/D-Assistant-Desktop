// Check the generated production graph, including all eager shared dependencies.
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib')
const dist = path.resolve(__dirname, '../frontend/dist')
const manifest = JSON.parse(fs.readFileSync(path.join(dist, '.vite/manifest.json'), 'utf8'))
const entries = Object.keys(manifest).filter(key => manifest[key].isEntry)
if (!entries.length) throw new Error('Build the frontend with its Vite manifest first')
const visited = new Set(), files = new Set()
function eager(key) {
  if (visited.has(key)) return
  visited.add(key)
  const chunk = manifest[key]
  if (!chunk) throw new Error('Missing static import in production manifest: ' + key)
  if (chunk.file.endsWith('.js')) files.add(chunk.file)
  for (const dependency of chunk.imports || []) eager(dependency)
  // dynamicImports are deliberately deferred until a feature is requested.
}
for (const entry of entries) eager(entry)
const buffers = [...files].map(file => fs.readFileSync(path.join(dist, file)))
const initialJSBytes = buffers.reduce((sum, value) => sum + value.length, 0)
const initialGzipBytes = buffers.reduce((sum, value) => sum + zlib.gzipSync(value).length, 0)
const budgetBytes = 350 * 1024
console.log(JSON.stringify({ initialJSBytes, initialGzipBytes, budgetBytes, initialFiles: [...files] }, null, 2))
if (initialJSBytes > budgetBytes) throw new Error('Initial JavaScript exceeds the 350 KiB budget')
