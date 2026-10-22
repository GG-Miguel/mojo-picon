import { useCallback, useEffect, useState } from 'react'
import { Chat } from './components/Chat'
import { DayPanel } from './components/DayPanel'
import { EmailLogin } from './components/EmailLogin'
import { ConsentScreen, PrivacyDialog } from './components/Privacy'
import { ProfileForm } from './components/ProfileForm'
import {
  acceptConsent,
  ApiError,
  deleteAccount,
  getConsent,
  getDay,
  getProfile,
  putProfile,
  type ConsentState,
} from './lib/api'
import {
  authConfigured,
  checkVerified,
  devMode,
  resendVerification,
  signIn,
  signOut,
  watchSession,
  type Session,
} from './lib/auth'
import type { Day, Profile } from './lib/types'

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [hasProfile, setHasProfile] = useState<boolean | undefined>(undefined)
  const [day, setDay] = useState<Day | null>(null)
  const [editing, setEditing] = useState<Profile | null>(null) // open profile editor (chat stays mounted)
  const [consent, setConsent] = useState<ConsentState | undefined>(undefined)
  const [privacyOpen, setPrivacyOpen] = useState(false)

  useEffect(() => watchSession(setSession), [])

  const refreshDay = useCallback(async () => {
    if (session) setDay(await getDay(await session.token()))
  }, [session])

  useEffect(() => {
    if (!session?.verified) return
    session
      .token()
      .then(getConsent)
      .then(setConsent)
      .catch(() => setConsent(undefined))
  }, [session])

  useEffect(() => {
    if (!session?.verified || !consent?.accepted) return
    session
      .token()
      .then(getProfile)
      .then(() => {
        setHasProfile(true)
        return refreshDay()
      })
      .catch((e) => setHasProfile(e instanceof ApiError && e.status === 404 ? false : undefined))
  }, [session, consent, refreshDay])

  if (session === undefined) return <Centered>Cargando…</Centered>
  if (!authConfigured)
    return <Centered>Falta la configuración de Firebase (ver frontend/.env.example).</Centered>
  if (session === null) {
    return (
      <Centered>
        <h1 className="text-4xl font-bold text-picon">Mojo Picón</h1>
        <p className="text-stone-500">dale sabor a tu vida</p>
        <button onClick={signIn} className="mt-6 rounded-full bg-picon px-6 py-2 font-medium text-white">
          Entrar con Google
        </button>
        <p className="mt-4 text-sm text-stone-400">o con tu email</p>
        <EmailLogin />
        <AiNotice />
      </Centered>
    )
  }
  if (!session.verified) {
    return <VerifyEmail onVerified={(s) => setSession(s)} session={session} />
  }
  if (consent === undefined) return <Centered>Cargando…</Centered>
  if (!consent.accepted) {
    return (
      <ConsentScreen
        contact={consent.contact}
        onAccept={async () =>
          setConsent(await acceptConsent(await session.token(), consent.required_version))
        }
        onLeave={signOut}
      />
    )
  }

  return (
    <div className="flex h-full flex-col bg-stone-50 text-stone-800">
      <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-2">
        <h1 className="font-bold text-picon">
          Mojo <span className="font-normal text-cilantro">Picón</span>
        </h1>
        <div className="flex items-center gap-3 text-sm text-stone-500">
          {hasProfile && (
            <button
              onClick={async () => setEditing(await getProfile(await session.token()))}
              className="underline"
            >
              Perfil
            </button>
          )}
          <button onClick={() => setPrivacyOpen(true)} className="underline">
            Privacidad
          </button>
          <span className="max-sm:hidden">{session.name}</span>
          {!devMode && (
            <button onClick={signOut} className="underline">
              Salir
            </button>
          )}
        </div>
      </header>
      {hasProfile === false ? (
        <ProfileForm
          onSave={async (profile) => {
            await putProfile(await session.token(), profile)
            setHasProfile(true)
            await refreshDay()
          }}
        />
      ) : (
        <main className="flex min-h-0 flex-1 flex-col md:flex-row">
          <Chat token={session.token} onDayUpdated={refreshDay} />
          <div className="border-stone-200 bg-white md:w-80 md:border-l max-md:border-t max-md:max-h-[40%] max-md:overflow-y-auto">
            <DayPanel day={day} />
          </div>
        </main>
      )}
      {editing && (
        <div className="fixed inset-0 z-10 overflow-y-auto bg-stone-900/40 p-4">
          <div className="mx-auto max-w-md rounded-2xl bg-white shadow-lg">
            <ProfileForm
              initial={editing}
              onCancel={() => setEditing(null)}
              onSave={async (profile) => {
                await putProfile(await session.token(), profile)
                setEditing(null)
                await refreshDay() // new targets for the day
              }}
            />
          </div>
        </div>
      )}
      {privacyOpen && (
        <PrivacyDialog
          contact={consent.contact}
          onClose={() => setPrivacyOpen(false)}
          onDelete={async () => {
            await deleteAccount(await session.token())
            setPrivacyOpen(false)
            setHasProfile(undefined)
            setConsent({ ...consent, accepted: false, version: null }) // nothing left: back to the terms
            await signOut()
          }}
        />
      )}
      <footer className="border-t border-stone-200 bg-white px-4 py-1">
        <AiNotice />
      </footer>
    </div>
  )
}

function AiNotice() {
  return (
    <p className="mt-2 text-center text-xs text-stone-400">
      Estás hablando con una inteligencia artificial. Mojo da orientación general, no sustituye a un
      profesional sanitario.
    </p>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 p-6 text-center">{children}</div>
  )
}

/** An email account whose address is not confirmed yet: the API rejects it until it is. */
function VerifyEmail({ session, onVerified }: { session: Session; onVerified: (s: Session) => void }) {
  const [message, setMessage] = useState('')
  return (
    <Centered>
      <h1 className="text-2xl font-bold text-picon">Confirma tu email</h1>
      <p className="max-w-xs text-center text-stone-600">
        Te hemos enviado un enlace a {session.name}. Ábrelo y vuelve aquí.
      </p>
      <button
        onClick={async () =>
          (await checkVerified())
            ? onVerified({ ...session, verified: true })
            : setMessage('Todavía no consta como confirmado.')
        }
        className="mt-4 rounded-full bg-picon px-6 py-2 font-medium text-white"
      >
        Ya lo he confirmado
      </button>
      <div className="mt-2 flex gap-3 text-sm text-stone-500">
        <button
          onClick={async () => {
            await resendVerification()
            setMessage('Enlace reenviado.')
          }}
          className="underline"
        >
          Reenviar el enlace
        </button>
        <button onClick={signOut} className="underline">
          Salir
        </button>
      </div>
      {message && <p className="text-sm text-stone-600">{message}</p>}
    </Centered>
  )
}
