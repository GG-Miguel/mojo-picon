import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider,
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from 'firebase/auth'

const devToken = import.meta.env.VITE_DEV_TOKEN as string | undefined
const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

export const devMode = Boolean(devToken)
const auth = devMode || !config.apiKey ? null : getAuth(initializeApp(config))

export type Session = { name: string; token: () => Promise<string> }

/** Calls back with the signed-in session, or null. In dev mode the session is the dev token. */
export function watchSession(callback: (session: Session | null) => void): () => void {
  if (devMode) {
    callback({ name: 'Desarrollo', token: async () => devToken as string })
    return () => {}
  }
  if (!auth) {
    callback(null)
    return () => {}
  }
  return onAuthStateChanged(auth, (user: User | null) =>
    callback(
      user ? { name: user.displayName ?? user.email ?? 'Usuario', token: () => user.getIdToken() } : null,
    ),
  )
}

export const authConfigured = devMode || auth !== null

export async function signIn(): Promise<void> {
  if (auth) await signInWithPopup(auth, new GoogleAuthProvider())
}

export async function signOut(): Promise<void> {
  if (auth) await firebaseSignOut(auth)
}
