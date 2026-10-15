import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import Markdown, { type Components } from 'react-markdown'

/** HTTP(S) links only (doc 13); anything else renders as plain text. */
export function safeUrl(url: string): string {
  try {
    const u = new URL(url)
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : ''
  } catch {
    return ''
  }
}

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="relative my-2">
      <pre className="overflow-x-auto rounded-control border border-border bg-canvas p-3 text-[14px]">
        <code>{code}</code>
      </pre>
      <button
        type="button"
        onClick={async () => {
          await navigator.clipboard.writeText(code) // code only, no attribution
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        className="absolute top-1.5 right-1.5 inline-flex min-h-8 items-center gap-1 rounded-control border border-border bg-surface px-2 text-[12px] text-muted hover:text-text"
      >
        {copied ? <Check aria-hidden size={14} /> : <Copy aria-hidden size={14} />}
        {copied ? 'Copied' : 'Copy code'}
      </button>
    </div>
  )
}

const components: Components = {
  a: ({ href, children }) => {
    const url = safeUrl(href ?? '')
    if (!url) return <span>{children}</span>
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className="underline">
        {children}
      </a>
    )
  },
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children }) => {
    const text = String(children ?? '')
    if (className || text.includes('\n')) return <CodeBlock code={text.replace(/\n$/, '')} />
    return <code className="rounded bg-surface-subtle px-1 py-0.5 text-[0.92em]">{children}</code>
  },
  img: ({ alt }) => <span>{alt}</span>, // no remote images inside replies
  ul: ({ children }) => <ul className="my-1 list-disc pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 list-decimal pl-5">{children}</ol>,
  p: ({ children }) => <p className="my-1 [overflow-wrap:anywhere]">{children}</p>,
}

/** Model and user text as sanitized Markdown: no raw HTML, safe links, wrapping long lines. */
export function MarkdownText({ text }: { text: string }) {
  return (
    <div className="min-w-0 [overflow-wrap:anywhere]">
      <Markdown components={components} skipHtml urlTransform={(u) => safeUrl(u) || ''}>
        {text}
      </Markdown>
    </div>
  )
}
