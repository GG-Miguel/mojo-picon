import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
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

/** verified: false for an email account whose address is not confirmed yet (the API rejects it). */
export type Session = { name: string; verified: boolean; token: () => Promise<string> }

/** Calls back with the signed-in session, or null. In dev mode the session is the dev token. */
export function watchSession(callback: (session: Session | null) => void): () => void {
  if (devMode) {
    callback({ name: 'Desarrollo', verified: true, token: async () => devToken as string })
    return () => {}
  }
  if (!auth) {
    callback(null)
    return () => {}
  }
  return onAuthStateChanged(auth, (user: User | null) => callback(user ? toSession(user) : null))
}

function toSession(user: User): Session {
  const password = user.providerData.some((p) => p.providerId === 'password')
  return {
    name: user.displayName ?? user.email ?? 'Usuario',
    verified: !password || user.emailVerified,
    token: () => user.getIdToken(),
  }
}

export const authConfigured = devMode || auth !== null

export async function signIn(): Promise<void> {
  if (auth) await signInWithPopup(auth, new GoogleAuthProvider())
}

/** Messages for the Firebase errors a user can cause (the rest: a generic one). */
const ERRORS: Record<string, string> = {
  'auth/invalid-credential': 'Email o contraseña incorrectos.',
  'auth/invalid-email': 'El email no es válido.',
  'auth/email-already-in-use': 'Ya hay una cuenta con ese email: entra o recupera la contraseña.',
  'auth/weak-password': 'La contraseña debe tener al menos 8 caracteres.',
  'auth/too-many-requests': 'Demasiados intentos. Espera unos minutos.',
  'auth/operation-not-allowed': 'El acceso con email no está activado todavía.',
}

export function authMessage(error: unknown): string {
  const code = (error as { code?: string })?.code ?? ''
  return ERRORS[code] ?? 'No se ha podido completar. Inténtalo de nuevo.'
}

export async function signInWithEmail(email: string, password: string): Promise<void> {
  if (auth) await signInWithEmailAndPassword(auth, email.trim(), password)
}

/** Creates the account and sends the verification email; the app waits until it is confirmed. */
export async function signUpWithEmail(email: string, password: string): Promise<void> {
  if (password.length < 8) throw { code: 'auth/weak-password' }
  if (!auth) return
  const { user } = await createUserWithEmailAndPassword(auth, email.trim(), password)
  await sendEmailVerification(user)
}

export async function resendVerification(): Promise<void> {
  if (auth?.currentUser) await sendEmailVerification(auth.currentUser)
}

/** Reloads the user after they click the link; true if the email is now verified. */
export async function checkVerified(): Promise<boolean> {
  const user = auth?.currentUser
  if (!user) return false
  await user.reload()
  await user.getIdToken(true) // a fresh token carries email_verified for the API
  return user.emailVerified
}

export async function resetPassword(email: string): Promise<void> {
  if (auth) await sendPasswordResetEmail(auth, email.trim())
}

export async function signOut(): Promise<void> {
  if (auth) await firebaseSignOut(auth)
}
