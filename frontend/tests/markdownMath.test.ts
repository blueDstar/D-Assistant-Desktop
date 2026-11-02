import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeMarkdownMath } from '../src/markdownMath.ts'

test('model inline and display math delimiters keep Vietnamese and Japanese text', () => {
  assert.equal(normalizeMarkdownMath('Lực \\(F=ma\\). 日本語'), 'Lực $F=ma$. 日本語')
  assert.equal(normalizeMarkdownMath('\\[x^2\n+y^2\\]'), '\n$$\nx^2\n+y^2\n$$\n')
})

test('math normalization does not rewrite fenced code or existing dollar math', () => {
  const source = '```python\nprint("\\(x\\)")\n```\n$y$ và \\(z\\)'
  assert.equal(normalizeMarkdownMath(source), '```python\nprint("\\(x\\)")\n```\n$y$ và $z$')
})
