import type { ChatEvent, Day, Profile } from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  return (await response.json()) as T
}

export type ConsentState = {
  accepted: boolean
  version: string | null
  required_version: string
  contact: string
}

export const getConsent = (token: string) => request<ConsentState>(token, '/me/consent')
export const acceptConsent = (token: string, version: string) =>
  request<ConsentState>(token, '/me/consent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version }),
  })
export const deleteAccount = (token: string) =>
  request<{ deleted: boolean; traces_deleted: number | null }>(token, '/me', { method: 'DELETE' })

export const getDay = (token: string) => request<Day>(token, '/day')
export const getProfile = (token: string) => request<Profile>(token, '/me/profile')
export const putProfile = (token: string, profile: Profile) =>
  request<Profile>(token, '/me/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })

/**
 * POST /chat and read the Server-Sent Events as they arrive. EventSource is not used: it does not
 * support POST or the Authorization header (API y frontend: Contrato de eventos).
 */
export async function streamChat(
  token: string,
  message: string,
  sessionId: string | null,
  onEvent: (event: ChatEvent) => void,
  photo: File | null = null,
): Promise<void> {
  const form = new FormData()
  form.append('message', message)
  if (sessionId) form.append('session_id', sessionId)
  if (photo) form.append('photo', photo)
  const response = await fetch('/chat', {
    method: 'POST',
    body: form,
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok || !response.body) throw new ApiError(response.status, await response.text())

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let end: number
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      if (data) onEvent(JSON.parse(data) as ChatEvent)
    }
  }
}
