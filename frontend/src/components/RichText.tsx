import { Fragment, type ReactNode } from 'react'

/** Minimal Markdown for the Coach's answers: paragraphs, "- " lists (also right after a line of
 * text) and **bold**. React escapes everything else, so model output can never inject HTML
 * (OWASP: insecure output handling). */
export function RichText({ text }: { text: string }) {
  const out: ReactNode[] = []
  let paragraph: string[] = []
  let list: string[] = []
  const flush = () => {
    if (paragraph.length) {
      out.push(
        <p key={out.length}>
          {paragraph.map((l, j) => (
            <Fragment key={j}>
              {j > 0 && <br />}
              {bold(l)}
            </Fragment>
          ))}
        </p>,
      )
    }
    if (list.length) {
      out.push(
        <ul key={out.length} className="list-disc space-y-0.5 pl-5">
          {list.map((l, j) => (
            <li key={j}>{bold(l)}</li>
          ))}
        </ul>,
      )
    }
    paragraph = []
    list = []
  }
  for (const line of text.split('\n')) {
    const item = line.match(/^\s*[-*] (.*)$/)
    if (!line.trim()) flush()
    else if (item) {
      if (paragraph.length) {
        const pending = list
        list = []
        flush()
        list = pending
      }
      list.push(item[1])
    } else {
      if (list.length) flush()
      paragraph.push(line)
    }
  }
  flush()
  return <div className="space-y-2">{out}</div>
}

function bold(line: string) {
  return line.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : part))
}
