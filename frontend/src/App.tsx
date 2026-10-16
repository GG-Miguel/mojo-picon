import { useCallback, useEffect, useState } from 'react'
import { Chat } from './components/Chat'
import { DayPanel } from './components/DayPanel'
import { ProfileForm } from './components/ProfileForm'
import { ApiError, getDay, getProfile, putProfile } from './lib/api'
import { authConfigured, devMode, signIn, signOut, watchSession, type Session } from './lib/auth'
import type { Day, Profile } from './lib/types'

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [hasProfile, setHasProfile] = useState<boolean | undefined>(undefined)
  const [day, setDay] = useState<Day | null>(null)
  const [editing, setEditing] = useState<Profile | null>(null) // open profile editor (chat stays mounted)

  useEffect(() => watchSession(setSession), [])

  const refreshDay = useCallback(async () => {
    if (session) setDay(await getDay(await session.token()))
  }, [session])

  useEffect(() => {
    if (!session) return
    session
      .token()
      .then(getProfile)
      .then(() => {
        setHasProfile(true)
        return refreshDay()
      })
      .catch((e) => setHasProfile(e instanceof ApiError && e.status === 404 ? false : undefined))
  }, [session, refreshDay])

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
        <AiNotice />
      </Centered>
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
