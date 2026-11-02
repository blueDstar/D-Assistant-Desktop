/** Normalize model math delimiters while preserving fenced code verbatim. */
export function normalizeMarkdownMath(text: string): string {
  return text.split('```').map((part, index) => index % 2 ? part : part
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => '\n$$\n' + math + '\n$$\n')
    .replace(/\\\((.*?)\\\)/g, (_, math) => '$' + math + '$')).join('```')
}
