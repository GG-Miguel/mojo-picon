// Mirrors src/mojo_picon/api/events.py and the /day response (generated from OpenAPI later).

export type StepEvent = {
  type: 'step'
  id: string
  label: string
  status: 'start' | 'done' | 'failed'
  detail: string
}
export type SourceRef = { title: string; url: string; tags: string[] }
export type FinalEvent = { type: 'final'; text: string; session_id: string; sources?: SourceRef[] }
export type ChatEvent =
  | StepEvent
  | FinalEvent
  | { type: 'ask'; text: string }
  | { type: 'day_updated' }
  | { type: 'trace'; url: string }
  | { type: 'error'; message: string }

export type Macros = { kcal: number; protein_g: number; carbs_g: number; fat_g: number }
export type Nutrients = Macros & { sugars_g: number; fiber_g: number; sodium_mg: number }

export type DayEntry =
  | {
      kind: 'meal'
      id: string
      timestamp: string
      nutrients: Nutrients
      items: { food_id: string; grams: number; name?: string }[]
    }
  | {
      kind: 'activity'
      id: string
      timestamp: string
      activity_id: string
      minutes: number
      kcal: number
      name?: string
    }

export type Day = {
  balance: {
    day: string
    target: { target: Macros; training_kcal: number }
    consumed: Nutrients
    remaining: Macros
    meals: number
    activities: number
  }
  entries: DayEntry[]
}

export type Profile = {
  age: number
  sex: 'male' | 'female'
  weight_kg: number
  height_cm: number
  activity_level: 'sedentary' | 'light' | 'moderate' | 'high'
  goal: 'maintain' | 'lose' | 'gain'
  weekly_rate_kg: number
  allergens: string[]
  timezone: string
}
