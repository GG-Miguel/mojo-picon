import { useState } from 'react'
import type { Profile } from '../lib/types'

const ALLERGENS: [string, string][] = [
  ['gluten', 'Gluten'],
  ['milk', 'Leche'],
  ['eggs', 'Huevo'],
  ['fish', 'Pescado'],
  ['crustaceans', 'Crustáceos'],
  ['molluscs', 'Moluscos'],
  ['peanuts', 'Cacahuete'],
  ['tree_nuts', 'Frutos de cáscara'],
  ['soy', 'Soja'],
  ['sesame', 'Sésamo'],
  ['celery', 'Apio'],
  ['mustard', 'Mostaza'],
  ['sulphites', 'Sulfitos'],
  ['lupin', 'Altramuz'],
]

type NumberField = 'age' | 'weight_kg' | 'height_cm' | 'weekly_rate_kg'

// The same limits as the API (domain/profile.py)
const RANGES: Record<NumberField, { min: number; max: number; decimals: boolean; message: string }> = {
  age: { min: 18, max: 100, decimals: false, message: 'La edad debe estar entre 18 y 100 años.' },
  weight_kg: { min: 30.1, max: 299.9, decimals: true, message: 'El peso debe estar entre 30 y 300 kg.' },
  height_cm: { min: 120.1, max: 249.9, decimals: true, message: 'La altura debe estar entre 120 y 250 cm.' },
  weekly_rate_kg: {
    min: 0,
    max: 1,
    decimals: true,
    message: 'El ritmo debe estar entre 0 y 1 kg por semana (p. ej. 0,5).',
  },
}

/** "0,5" or "0.5" -> 0.5; null if it is not a number in range (or has decimals where none fit). */
function parse(key: NumberField, raw: string): number | null {
  const clean = raw.trim().replace(',', '.')
  if (!/^\d+(\.\d+)?$/.test(clean)) return null
  const value = Number(clean)
  const { min, max, decimals } = RANGES[key]
  if (!decimals && !Number.isInteger(value)) return null
  return value >= min && value <= max ? value : null
}

export function ProfileForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Profile
  onSave: (profile: Profile) => Promise<void>
  onCancel?: () => void
}) {
  const [p, setP] = useState<Profile>(
    initial ?? {
      age: 30,
      sex: 'female',
      weight_kg: 65,
      height_cm: 168,
      activity_level: 'light',
      goal: 'maintain',
      weekly_rate_kg: 0.5,
      allergens: [],
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Atlantic/Canary',
    },
  )
  // Number fields keep the text as typed: converting on every key turned an empty field into "0",
  // dropped the "." of "0." and rejected the Spanish decimal comma ("0,5"). Parsed on submit.
  const [text, setText] = useState<Record<NumberField, string>>({
    age: String(p.age),
    weight_kg: String(p.weight_kg),
    height_cm: String(p.height_cm),
    weekly_rate_kg: String(p.weekly_rate_kg).replace('.', ','),
  })
  const [error, setError] = useState('')
  const set = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setP((old) => ({ ...old, [key]: value }))
  const num = (key: NumberField) => (
    <input
      type="text"
      inputMode={RANGES[key].decimals ? 'decimal' : 'numeric'}
      autoComplete="off"
      value={text[key]}
      onChange={(e) => setText((old) => ({ ...old, [key]: e.target.value }))}
      aria-invalid={parse(key, text[key]) === null}
      className="w-full rounded border border-stone-300 px-2 py-1 aria-[invalid=true]:border-picon"
    />
  )

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const values = {} as Record<NumberField, number>
    for (const key of Object.keys(RANGES) as NumberField[]) {
      if (key === 'weekly_rate_kg' && p.goal === 'maintain') {
        values[key] = 0
        continue
      }
      const value = parse(key, text[key])
      if (value === null) {
        setError(RANGES[key].message)
        return
      }
      values[key] = value
    }
    setError('')
    try {
      await onSave({ ...p, ...values })
    } catch {
      setError('No he podido guardar el perfil. Revisa los datos e inténtalo de nuevo.')
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-md space-y-3 p-6">
      <h2 className="text-xl font-semibold">{initial ? 'Tu perfil' : 'Cuéntame un poco de ti'}</h2>
      <p className="text-sm text-stone-500">Con estos datos el código calcula tu gasto y tus objetivos.</p>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <label>Edad {num('age')}</label>
        <label>
          Sexo
          <select
            value={p.sex}
            onChange={(e) => set('sex', e.target.value as Profile['sex'])}
            className="w-full rounded border border-stone-300 px-2 py-1"
          >
            <option value="female">Mujer</option>
            <option value="male">Hombre</option>
          </select>
        </label>
        <label>Peso (kg) {num('weight_kg')}</label>
        <label>Altura (cm) {num('height_cm')}</label>
        <label>
          Actividad diaria (sin entrenos)
          <select
            value={p.activity_level}
            onChange={(e) => set('activity_level', e.target.value as Profile['activity_level'])}
            className="w-full rounded border border-stone-300 px-2 py-1"
          >
            <option value="sedentary">Sedentaria</option>
            <option value="light">Ligera</option>
            <option value="moderate">Moderada</option>
            <option value="high">Alta</option>
          </select>
        </label>
        <label>
          Objetivo
          <select
            value={p.goal}
            onChange={(e) => set('goal', e.target.value as Profile['goal'])}
            className="w-full rounded border border-stone-300 px-2 py-1"
          >
            <option value="maintain">Mantener</option>
            <option value="lose">Perder peso</option>
            <option value="gain">Ganar peso</option>
          </select>
        </label>
        {p.goal !== 'maintain' && <label>Kg por semana (máx. 1) {num('weekly_rate_kg')}</label>}
      </div>
      <fieldset className="text-sm">
        <legend className="mb-1">Alergias</legend>
        <div className="flex flex-wrap gap-2">
          {ALLERGENS.map(([id, name]) => (
            <label key={id} className="flex items-center gap-1 rounded border border-stone-200 px-2 py-0.5">
              <input
                type="checkbox"
                checked={p.allergens.includes(id)}
                onChange={(e) =>
                  set(
                    'allergens',
                    e.target.checked ? [...p.allergens, id] : p.allergens.filter((a) => a !== id),
                  )
                }
              />
              {name}
            </label>
          ))}
        </div>
      </fieldset>
      {error && <p className="text-sm text-picon">{error}</p>}
      <div className="flex gap-2">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-full border border-stone-300 py-2 font-medium text-stone-600"
          >
            Cancelar
          </button>
        )}
        <button className="flex-1 rounded-full bg-picon py-2 font-medium text-white">Guardar</button>
      </div>
    </form>
  )
}
