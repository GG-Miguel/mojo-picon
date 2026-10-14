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

export function ProfileForm({ onSave }: { onSave: (profile: Profile) => Promise<void> }) {
  const [p, setP] = useState<Profile>({
    age: 30,
    sex: 'female',
    weight_kg: 65,
    height_cm: 168,
    activity_level: 'light',
    goal: 'maintain',
    weekly_rate_kg: 0.5,
    allergens: [],
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Atlantic/Canary',
  })
  const [error, setError] = useState('')
  const set = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setP((old) => ({ ...old, [key]: value }))
  const num = (key: 'age' | 'weight_kg' | 'height_cm' | 'weekly_rate_kg') => (
    <input
      type="number"
      step="any"
      value={p[key]}
      onChange={(e) => set(key, Number(e.target.value))}
      className="w-full rounded border border-stone-300 px-2 py-1"
    />
  )

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      await onSave(p)
    } catch {
      setError('Revisa los datos: edad entre 18 y 100 y un ritmo de como mucho 1 kg por semana.')
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-md space-y-3 p-6">
      <h2 className="text-xl font-semibold">Cuéntame un poco de ti</h2>
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
      <button className="w-full rounded-full bg-picon py-2 font-medium text-white">Guardar</button>
    </form>
  )
}
