import { useRef, useState } from 'react'
import { streamChat } from '../lib/api'
import type { StepEvent } from '../lib/types'
import { RichText } from './RichText'

type Turn = {
  user: string
  steps: StepEvent[]
  answer?: string
  trace?: string
  error?: string
}

export function Chat({ token, onDayUpdated }: { token: () => Promise<string>; onDayUpdated: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const sessionId = useRef<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const update = (fn: (turn: Turn) => Turn) =>
    setTurns((all) => [...all.slice(0, -1), fn(all[all.length - 1])])

  async function send(event: React.FormEvent) {
    event.preventDefault()
    const message = input.trim()
    if (!message || busy) return
    setInput('')
    setBusy(true)
    setTurns((all) => [...all, { user: message, steps: [] }])
    try {
      await streamChat(await token(), message, sessionId.current, (e) => {
        if (e.type === 'step') {
          update((t) => {
            const others = t.steps.filter((s) => s.id !== e.id)
            return { ...t, steps: [...others, e] }
          })
        } else if (e.type === 'final') {
          sessionId.current = e.session_id
          update((t) => ({ ...t, answer: e.text }))
        } else if (e.type === 'trace') {
          update((t) => ({ ...t, trace: e.url }))
        } else if (e.type === 'day_updated') {
          onDayUpdated()
        } else if (e.type === 'error') {
          update((t) => ({ ...t, error: e.message }))
        }
        bottom.current?.scrollIntoView({ behavior: 'smooth' })
      })
    } catch {
      update((t) => ({ ...t, error: 'No he podido conectar con Mojo. Inténtalo de nuevo.' }))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-5 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="mx-auto mt-10 max-w-md text-center text-stone-500">
            <p className="text-lg">¿Qué has comido hoy? ¿Vas a entrenar?</p>
            <p className="mt-2 text-sm">
              Prueba: «He desayunado dos tostadas con aceite» o «Esta tarde corro 10 km, ¿qué ceno?»
            </p>
          </div>
        )}
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-picon px-4 py-2 text-white">
              {turn.user}
            </div>
            {turn.steps.length > 0 && <Steps steps={turn.steps} />}
            {turn.answer !== undefined && (
              <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm">
                <RichText text={turn.answer} />
                {turn.trace && (
                  <a
                    className="mt-2 block text-xs text-stone-400 underline"
                    href={turn.trace}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Ver traza en Langfuse
                  </a>
                )}
              </div>
            )}
            {turn.error && <p className="text-sm text-picon">{turn.error}</p>}
          </div>
        ))}
        {busy && <p className="animate-pulse text-sm text-stone-400">Mojo está pensando…</p>}
        <div ref={bottom} />
      </div>
      <form onSubmit={send} className="flex gap-2 border-t border-stone-200 bg-white p-3">
        <button
          type="button"
          disabled
          title="Análisis de fotos: próximamente"
          className="shrink-0 rounded-full px-2 text-xl opacity-40"
          aria-label="Subir foto (próximamente)"
        >
          📷
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={2000}
          placeholder="Escribe un mensaje…"
          className="min-w-0 flex-1 rounded-full border border-stone-300 px-4 py-2 outline-none focus:border-picon"
        />
        <button
          disabled={busy || !input.trim()}
          className="shrink-0 rounded-full bg-picon px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          Enviar
        </button>
      </form>
    </section>
  )
}

function Steps({ steps }: { steps: StepEvent[] }) {
  return (
    <details className="max-w-[85%] text-sm text-stone-500" open>
      <summary className="cursor-pointer select-none">▸ {steps.length} pasos del agente</summary>
      <ul className="mt-1 space-y-0.5 pl-4">
        {steps.map((s) => (
          <li key={s.id}>
            {s.status === 'start' ? '⏳' : s.status === 'done' ? '✓' : '✗'} {s.label}
            {s.detail && <span className="text-stone-400"> · {s.detail}</span>}
          </li>
        ))}
      </ul>
    </details>
  )
}
