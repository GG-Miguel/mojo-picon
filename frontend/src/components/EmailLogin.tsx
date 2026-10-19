import { useState } from 'react'
import { authMessage, resetPassword, signInWithEmail, signUpWithEmail } from '../lib/auth'

type Mode = 'signin' | 'signup' | 'reset'

/** Email and password access, besides Google. New accounts must verify their email (the API checks it). */
export function EmailLogin() {
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      if (mode === 'signin') await signInWithEmail(email, password)
      if (mode === 'signup') await signUpWithEmail(email, password)
      if (mode === 'reset') {
        await resetPassword(email)
        setMessage('Si hay una cuenta con ese email, te hemos enviado un enlace para cambiar la contraseña.')
      }
    } catch (e) {
      setMessage(authMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const label = { signin: 'Entrar', signup: 'Crear cuenta', reset: 'Enviar enlace' }[mode]
  return (
    <form onSubmit={submit} className="mt-4 flex w-full max-w-xs flex-col gap-2 text-sm">
      <input
        type="email"
        required
        autoComplete="email"
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="rounded border border-stone-300 px-3 py-2"
      />
      {mode !== 'reset' && (
        <input
          type="password"
          required
          minLength={mode === 'signup' ? 8 : undefined}
          autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
          placeholder={mode === 'signup' ? 'Contraseña (mínimo 8 caracteres)' : 'Contraseña'}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-stone-300 px-3 py-2"
        />
      )}
      <button
        type="submit"
        disabled={busy}
        className="rounded-full border border-picon px-6 py-2 font-medium text-picon disabled:opacity-50"
      >
        {label}
      </button>
      {message && <p className="text-center text-stone-600">{message}</p>}
      <div className="flex justify-center gap-3 text-stone-500">
        {mode !== 'signin' && (
          <button type="button" onClick={() => setMode('signin')} className="underline">
            Ya tengo cuenta
          </button>
        )}
        {mode !== 'signup' && (
          <button type="button" onClick={() => setMode('signup')} className="underline">
            Crear cuenta
          </button>
        )}
        {mode === 'signin' && (
          <button type="button" onClick={() => setMode('reset')} className="underline">
            He olvidado la contraseña
          </button>
        )}
      </div>
    </form>
  )
}
