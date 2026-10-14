import type { Day } from '../lib/types'

const fmt = (n: number) => Math.round(n).toLocaleString('es-ES')

export function DayPanel({ day }: { day: Day | null }) {
  if (!day) return <aside className="p-4 text-stone-400">Cargando el día…</aside>
  const { target, consumed, remaining } = day.balance
  const pct = Math.min(1, consumed.kcal / Math.max(target.target.kcal, 1))
  const macros: [string, number, number][] = [
    ['Proteína', consumed.protein_g, target.target.protein_g],
    ['Hidratos', consumed.carbs_g, target.target.carbs_g],
    ['Grasas', consumed.fat_g, target.target.fat_g],
  ]
  return (
    <aside className="space-y-5 overflow-y-auto p-4">
      <h2 className="font-semibold text-stone-700">Hoy</h2>
      <div className="flex items-center gap-4">
        <svg
          viewBox="0 0 36 36"
          className="h-28 w-28 -rotate-90"
          role="img"
          aria-label={`${fmt(consumed.kcal)} de ${fmt(target.target.kcal)} kcal`}
        >
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e7e5e4" strokeWidth="3.5" />
          <circle
            cx="18"
            cy="18"
            r="15.9"
            fill="none"
            stroke="var(--color-cilantro)"
            strokeWidth="3.5"
            strokeDasharray={`${pct * 100} 100`}
            strokeLinecap="round"
          />
        </svg>
        <div>
          <p className="text-3xl font-bold text-stone-800">{fmt(consumed.kcal)}</p>
          <p className="text-sm text-stone-500">de {fmt(target.target.kcal)} kcal</p>
          <p className="text-sm text-cilantro">quedan {fmt(remaining.kcal)} kcal</p>
          {target.training_kcal > 0 && (
            <p className="text-xs text-stone-400">incluye +{fmt(target.training_kcal)} kcal de entreno</p>
          )}
        </div>
      </div>
      <div className="space-y-2">
        {macros.map(([name, got, goal]) => (
          <div key={name}>
            <div className="flex justify-between text-sm text-stone-600">
              <span>{name}</span>
              <span>
                {fmt(got)} / {fmt(goal)} g
              </span>
            </div>
            <div className="h-2 rounded-full bg-stone-200">
              <div
                className="h-2 rounded-full bg-picon"
                style={{ width: `${Math.min(100, (got / Math.max(goal, 1)) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <ul className="space-y-1 text-sm text-stone-600">
        {day.entries.map((e) =>
          e.kind === 'meal' ? (
            <li key={e.id}>
              🍽 {e.items.map((i) => `${i.name ?? i.food_id} ${fmt(i.grams)} g`).join(', ')} ·{' '}
              {fmt(e.nutrients.kcal)} kcal
            </li>
          ) : (
            <li key={e.id}>
              🏃 {e.name ?? e.activity_id} · {fmt(e.minutes)} min · +{fmt(e.kcal)} kcal
            </li>
          ),
        )}
        {day.entries.length === 0 && <li className="text-stone-400">Aún no has registrado nada hoy.</li>}
      </ul>
    </aside>
  )
}
