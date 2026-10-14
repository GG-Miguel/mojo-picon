# Functional specification

What Mojo Picón does from the user's point of view. The app's interface is in Spanish, so user examples are kept in Spanish.

## Use cases

### UC-01 · Set up the profile
The user gives age, sex, weight, height, activity level, goal, allergies, intolerances and preferences. **The agent only asks for what is missing.**
- **Acceptance:** basal metabolic rate and daily expenditure are calculated by tools (Mifflin-St Jeor and activity factors); extreme goals are rejected with an explanation.
- **(Implementation note, 2026-10-12)** The activity level describes **daily life without training**; training sessions are logged as activities (UC-04) and added separately, so they are not counted twice. Activity factors (1.2 / 1.3 / 1.4 / 1.5) are **provisional**. A goal faster than 1 kg per week is rejected (`ExtremeGoalError`), and the daily target never goes below the BMR.

### UC-02 · Log a meal by text
«He desayunado dos tostadas con aceite y un café con leche».
- **Acceptance:** foods are identified in the database; ambiguous quantities are asked about; the day panel is updated.

### UC-03 · Log a meal by photo
The user uploads a photo of the dish.
- **Acceptance:** the agent returns foods with quantity **ranges** and a confidence; it asks about what cannot be seen (oil, sauces); it **only saves after the user confirms**; **EXIF metadata is removed** and **the photo is not stored**; if there is no food, it says so.
- **(Implementation note, 2026-10-14)** The vision extractor runs **before** the graph: JPEG, PNG or WebP up to 10 MB, re-encoded as JPEG (max 1024 px) without metadata. Its structured result is matched with `search_food` and appended to the user's message, marked as data and not instructions; the image itself never reaches the Coach, the session or the traces. If the analysis fails, the user is asked to describe the meal.

### UC-04 · Log activity
«Esta tarde corro 10 km» / «He hecho una hora de pesas».
- **Acceptance:** energy is calculated with MET tables and the user's weight; the day's target is adjusted.
- **(Implementation note, 2026-10-12)** The energy added is **net**: (MET − 1) × kg × hours, because the resting MET is already in the daily expenditure. MET values are **pending verification** against the Compendium of Physical Activities.

### UC-05 · Plan the rest of the day
«¿Qué ceno?» / the agent proposes it after a log.
- **Acceptance:** the proposal **passes `verify_plan`** (kcal ±10 %, macronutrients, allergens); if it does not, the agent corrects it (maximum 3 iterations); if it does not converge, it says so.
- **(Implementation note, 2026-10-12)** Macro tolerances are **provisional**: protein ±15 % (at least 10 g), carbs ±20 % (15 g), fat ±20 % (8 g). `verify_plan` also rejects unknown foods and unrealistic quantities.

### UC-06 · Questions with context
«¿Qué como antes de correr?» / «Estoy resfriado, ¿algo especial?».
- **Acceptance:** the answer uses retrieval and **cites the source**; the [guardrail policy](guardrails.md) applies.

### UC-07 · Risky case
«Estoy embarazada» / «Tengo diabetes tipo 1, ¿cuánta insulina?» / signs of an eating disorder.
- **Acceptance:** the system applies the right level (answer with a warning, or refer). It **never** gives medication guidance or diagnoses.

### UC-08 · Shopping list
«Hazme la lista para mañana y pasado».
- **Acceptance:** ingredients are added up, the pantry is subtracted, quantities are converted to shopping formats and grouped by supermarket section; the user can edit it by chatting; it can be downloaded or ticked off on a phone.

### UC-09 · Use Mojo Picón from another agent (MCP)
From an external agent (another framework, e.g. Google ADK): «apunta que he comido paella y dime cuánta proteína me queda».
- **Acceptance:** the meal is logged in **the diary of the token's owner**; the web panel shows it; a token cannot write to another user's diary.

### UC-10 · Data rights
The user exports or deletes their data.
- **Acceptance:** `GET /me/export` returns everything; `DELETE /me` deletes profile, diary, memory and associated traces.

### UC-11 · Delegate a query to Mojo Picón (A2A) · milestone 3
An external agent asks «¿qué ceno si mañana tengo carrera?».
- **Acceptance:** Mojo Picón reports progress, asks for the information it lacks and returns a verified plan with sources, with the same guardrails and authorization as the web. If it is not implemented, it remains a documented design.

## Non-functional requirements
| Requirement | Target |
|---|---|
| Latency | First visible event < 2 s; full turn < 30 s (with live progress) |
| Cost | < $0.10 per turn on average |
| Availability | Stable demo; backup video |
| Security | 0 accesses to another user's data in attack tests |
| Privacy | Data in the EU; personal data masked in traces |
| Language | Spanish |
| Accessibility | Usable on a phone (especially the shopping list) |

## Out of scope
Weekly menu; prices and budget; native mobile app; integration with Strava or sports watches; real users; fine-tuning.
