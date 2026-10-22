import { useState } from 'react'

/** The privacy policy: what is stored, where, for how long and how to exercise the rights. */
export function PrivacyPolicy({ contact }: { contact: string }) {
  const who = contact || 'el contacto indicado en la web'
  return (
    <div className="space-y-3 text-left text-sm text-stone-700">
      <h2 className="text-lg font-semibold text-picon">Política de privacidad</h2>
      <p>
        <b>Qué es Mojo Picón.</b> Un asistente de inteligencia artificial que da orientación general de
        alimentación para personas que hacen deporte. No es un dietista ni un profesional sanitario, no
        diagnostica ni trata ninguna enfermedad y sus respuestas no tienen valor de consejo médico ni
        vinculación legal. Ante cualquier duda de salud, consulta a un profesional. Si es urgente, llama al
        112.
      </p>
      <p>
        <b>Responsable y contacto.</b> El autor del proyecto, trabajo final del Máster en IA Generativa. Para
        cualquier cuestión sobre tus datos: {who}.
      </p>
      <p>
        <b>Qué datos guardamos.</b> Tu cuenta (email o cuenta de Google), tu perfil (edad, sexo, peso, altura,
        actividad, objetivo y alergias), lo que registras (comidas, entrenamientos, productos y recetas) y las
        conversaciones recientes. Las fotos no se guardan: se analizan en el momento y se les quitan los
        metadatos, como la ubicación.
      </p>
      <p>
        <b>Para qué.</b> Solo para darte el servicio: registrar lo que comes, calcular cifras, proponerte
        comidas y responder tus dudas. No vendemos tus datos ni los usamos para publicidad. Algunos de ellos,
        como las alergias, pueden considerarse datos de salud; por eso te pedimos tu consentimiento expreso,
        que puedes retirar en cualquier momento borrando tu cuenta.
      </p>
      <p>
        <b>Dónde están.</b> En Google Cloud, en la Unión Europea (servidor, base de datos y modelos de IA),
        con el inicio de sesión de Firebase (Google). Para vigilar que el servicio funciona bien se guarda una
        traza técnica de cada conversación en Langfuse, en su región de la UE. Las guías que consulta el
        asistente están en Qdrant (Fráncfort) y no contienen datos tuyos.
      </p>
      <p>
        <b>Cuánto tiempo.</b> Mientras tengas la cuenta. Al borrarla se eliminan tu perfil, tu diario, tus
        productos y recetas, tus conversaciones, sus trazas y la propia cuenta.
      </p>
      <p>
        <b>Tus derechos.</b> Puedes corregir tu perfil desde la app, borrar tu cuenta con el botón «Borrar mi
        cuenta» y pedir una copia de tus datos u oponerte a su tratamiento escribiendo a {who}. Si crees que
        no se respetan, puedes reclamar ante la Agencia Española de Protección de Datos (aepd.es).
      </p>
    </div>
  )
}

/** First visit: the terms, the privacy policy and an explicit acceptance (an unticked box). */
export function ConsentScreen({
  contact,
  onAccept,
  onLeave,
}: {
  contact: string
  onAccept: () => Promise<void>
  onLeave: () => void
}) {
  const [checked, setChecked] = useState(false)
  const [showPolicy, setShowPolicy] = useState(false)
  const [busy, setBusy] = useState(false)
  return (
    <div className="flex h-full flex-col items-center overflow-y-auto bg-stone-50 p-6">
      <div className="max-w-md space-y-4 rounded-2xl bg-white p-6 shadow">
        <h1 className="text-2xl font-bold text-picon">Antes de empezar</h1>
        <ul className="list-disc space-y-2 pl-5 text-left text-sm text-stone-700">
          <li>Mojo es una inteligencia artificial, no un dietista ni un profesional sanitario.</li>
          <li>
            Da orientación general sobre alimentación y deporte, sin valor de consejo médico ni vinculación
            legal.
          </li>
          <li>
            No diagnostica ni trata enfermedades: ante cualquier duda de salud, consulta a un profesional.
          </li>
          <li>
            Para funcionar guarda tu perfil, lo que registras y tus conversaciones, algunos de ellos datos que
            pueden considerarse de salud (como las alergias).
          </li>
        </ul>
        <button onClick={() => setShowPolicy(!showPolicy)} className="text-sm text-picon underline">
          {showPolicy ? 'Ocultar la política de privacidad' : 'Leer la política de privacidad'}
        </button>
        {showPolicy && <PrivacyPolicy contact={contact} />}
        <label className="flex items-start gap-2 text-left text-sm text-stone-700">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            className="mt-1"
          />
          <span>
            He leído y acepto estas condiciones y la política de privacidad, y consiento que se traten mis
            datos, incluidos los que puedan ser de salud, para usar Mojo Picón.
          </span>
        </label>
        <div className="flex items-center justify-between">
          <button onClick={onLeave} className="text-sm text-stone-500 underline">
            Salir
          </button>
          <button
            disabled={!checked || busy}
            onClick={async () => {
              setBusy(true)
              try {
                await onAccept()
              } finally {
                setBusy(false)
              }
            }}
            className="rounded-full bg-picon px-5 py-2 font-medium text-white disabled:opacity-40"
          >
            Aceptar y continuar
          </button>
        </div>
      </div>
    </div>
  )
}

/** The privacy policy with the right to erasure: delete the account and everything in it. */
export function PrivacyDialog({
  contact,
  onClose,
  onDelete,
}: {
  contact: string
  onClose: () => void
  onDelete: () => Promise<void>
}) {
  const [confirming, setConfirming] = useState(false)
  const [typed, setTyped] = useState('')
  const [error, setError] = useState('')
  return (
    <div className="fixed inset-0 z-20 overflow-y-auto bg-stone-900/40 p-4">
      <div className="mx-auto max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-lg">
        <PrivacyPolicy contact={contact} />
        <div className="border-t border-stone-200 pt-4">
          {!confirming ? (
            <button
              onClick={() => setConfirming(true)}
              className="text-sm font-medium text-red-700 underline"
            >
              Borrar mi cuenta
            </button>
          ) : (
            <div className="space-y-2 text-left text-sm">
              <p className="text-stone-700">
                Se borrarán tu perfil, tu diario, tus productos y recetas, tus conversaciones y tu cuenta. No
                se puede deshacer. Escribe <b>BORRAR</b> para confirmarlo.
              </p>
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                className="w-full rounded border border-stone-300 px-2 py-1"
              />
              <button
                disabled={typed !== 'BORRAR'}
                onClick={async () => {
                  try {
                    await onDelete()
                  } catch {
                    setError('No se ha podido borrar la cuenta. Inténtalo de nuevo o escribe al contacto.')
                  }
                }}
                className="rounded-full bg-red-700 px-4 py-1 font-medium text-white disabled:opacity-40"
              >
                Borrar definitivamente
              </button>
              {error && <p className="text-red-700">{error}</p>}
            </div>
          )}
        </div>
        <div className="text-right">
          <button onClick={onClose} className="text-sm text-stone-500 underline">
            Cerrar
          </button>
        </div>
      </div>
    </div>
  )
}
