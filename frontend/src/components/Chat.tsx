import { useEffect, useMemo, useRef, useState } from 'react'
import { streamChat } from '../lib/api'
import type { SourceRef, StepEvent } from '../lib/types'
import { RichText } from './RichText'

const MAX_PHOTO_BYTES = 10 * 1024 * 1024 // same limit as the API

type Turn = {
  user: string
  photo?: string // object URL of the photo, only for this page (never stored)
  steps: StepEvent[]
  answer?: string
  sources?: SourceRef[]
  trace?: string
  error?: string
}

export function Chat({ token, onDayUpdated }: { token: () => Promise<string>; onDayUpdated: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoError, setPhotoError] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const preview = useMemo(() => (photo ? URL.createObjectURL(photo) : ''), [photo])
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview)
    },
    [preview],
  )
  const sessionId = useRef<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const update = (fn: (turn: Turn) => Turn) =>
    setTurns((all) => [...all.slice(0, -1), fn(all[all.length - 1])])

  async function send(event: React.FormEvent) {
    event.preventDefault()
    const message = input.trim() || (photo ? 'Esto es lo que he comido.' : '')
    if (!message || busy) return
    const sent = photo
    setInput('')
    setPhoto(null)
    setBusy(true)
    setTurns((all) => [
      ...all,
      { user: message, steps: [], photo: sent ? URL.createObjectURL(sent) : undefined },
    ])
    try {
      await streamChat(
        await token(),
        message,
        sessionId.current,
        (e) => {
          if (e.type === 'step') {
            update((t) => {
              const others = t.steps.filter((s) => s.id !== e.id)
              return { ...t, steps: [...others, e] }
            })
          } else if (e.type === 'final') {
            sessionId.current = e.session_id
            update((t) => ({ ...t, answer: e.text, sources: e.sources }))
          } else if (e.type === 'trace') {
            update((t) => ({ ...t, trace: e.url }))
          } else if (e.type === 'day_updated') {
            onDayUpdated()
          } else if (e.type === 'error') {
            update((t) => ({ ...t, error: e.message }))
          }
          bottom.current?.scrollIntoView({ behavior: 'smooth' })
        },
        sent,
      )
    } catch {
      update((t) => ({ ...t, error: 'No he podido conectar con Mojo. Inténtalo de nuevo.' }))
    } finally {
      setBusy(false)
    }
  }

  function pickPhoto(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    event.target.value = ''
    if (file && file.size > MAX_PHOTO_BYTES) {
      setPhotoError('La foto es demasiado grande (máximo 10 MB).')
      return
    }
    setPhotoError('')
    setPhoto(file)
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
              {turn.photo && <img src={turn.photo} alt="Foto enviada" className="mb-2 max-h-48 rounded-lg" />}
              {turn.user}
            </div>
            {turn.steps.length > 0 && <Steps steps={turn.steps} />}
            {turn.answer !== undefined && (
              <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm">
                <RichText text={turn.answer} />
                {turn.sources && turn.sources.length > 0 && <Sources sources={turn.sources} />}
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
      {(photo || photoError) && (
        <div className="flex items-center gap-2 border-t border-stone-200 bg-white px-3 pt-2 text-sm">
          {photo && (
            <>
              <img src={preview} alt="Foto seleccionada" className="h-12 w-12 rounded object-cover" />
              <span className="min-w-0 flex-1 truncate text-stone-500">{photo.name}</span>
              <button
                type="button"
                onClick={() => setPhoto(null)}
                className="shrink-0 text-stone-400"
                aria-label="Quitar foto"
              >
                ✕
              </button>
            </>
          )}
          {photoError && <span className="text-picon">{photoError}</span>}
        </div>
      )}
      <form onSubmit={send} className="flex gap-2 border-t border-stone-200 bg-white p-3">
        <input
          ref={fileInput}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={pickPhoto}
          className="hidden"
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => fileInput.current?.click()}
          title="Analizar una foto del plato"
          className="shrink-0 rounded-full px-2 text-xl disabled:opacity-40"
          aria-label="Subir foto"
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
          disabled={busy || (!input.trim() && !photo)}
          className="shrink-0 rounded-full bg-picon px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          Enviar
        </button>
      </form>
    </section>
  )
}

function Sources({ sources }: { sources: SourceRef[] }) {
  return (
    <div className="mt-3 border-t border-stone-100 pt-2 text-xs text-stone-500">
      <p className="font-medium">Fuentes</p>
      <ul className="mt-1 space-y-1">
        {sources.map((s) => (
          <li key={s.url + s.title}>
            {/^https:\/\//.test(s.url) ? (
              <a className="underline" href={s.url} target="_blank" rel="noreferrer">
                {s.title}
              </a>
            ) : (
              s.title
            )}
            <span className="text-stone-400"> · {s.tags.join(' · ')}</span>
          </li>
        ))}
      </ul>
    </div>
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
