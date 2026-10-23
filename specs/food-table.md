# Food table

Curated table of about **200 foods** used by `search_food`, `get_nutrients`, `check_allergens`, `verify_plan` and the shopping list.

**Principle:** nutrient values are **never typed by hand** and **never invented by an LLM**. They come from official databases through a reproducible script (`data/build_foods.py`).

## Sources (in order of priority)
Revised on 2026-10-12 (ADR-25): **CIQUAL is the main source**; BEDCA is only used for six Spanish and Canary products that CIQUAL lacks. AESAN's authorisation was requested on 2026-10-12, and AESAN replied (October 2026) that this educational, non-commercial use is fine; `--no-bedca` remains for any other use.

| # | Source | Coverage | Access | Licence |
|---|---|---|---|---|
| 1 | **CIQUAL 2020** (ANSES, France) | ~3,200 foods, many Mediterranean | Full download (Excel/XML) from ciqual.anses.fr | **Etalab 2.0 open licence**: reuse, including commercial, with citation |
| 2 | **BEDCA** (AESAN) | 969 foods commonly eaten in Spain (957 with data) | Official XML query interface at bedca.net | **Personal, educational or non-commercial** use with mandatory attribution; **values may not be modified**; **reproduction in electronic format requires AESAN's express authorisation** |
| — | Recipes and approximations | Combinations of rows, close equivalents | Computed from the table | — |
| — | Open Food Facts | Packaged products by barcode | **Live lookup only**, not merged into the table | ODbL (kept out so the table does not inherit the share-alike obligation) |

Third source (decided 2026-10-12): UK **CoFID** (Open Government Licence) replaces USDA FoodData Central. Planned for milestone 2 as a quality check of CIQUAL (kcal differences above 20 % flagged) and for doubtful values.

### BEDCA conditions (important)
- **Mandatory attribution** in the app and in the report: *«AESAN/BEDCA Base de Datos Española de Composición de Alimentos v1.0 (2010)»*.
- **Values may not be modified.** BEDCA values are stored **as they are** (no rounding or conversion); fields we derive (e.g. salt from sodium) go in **separate columns marked as derived**.
- **Reproduction in electronic format requires express authorisation** (a CSV in the repository, and even more so a public repository, is such a reproduction). Each BEDCA row keeps a **fallback** (recipe or approximation) used with `--no-bedca`; the build report compares both.
- Commercial use would also need AESAN's authorisation.

### CIQUAL specifics
- CIQUAL 2020 gives no energy value for some foods (e.g. apple, lettuce, honey, nuts). Energy is then **derived** from the macronutrients with the factors of Regulation (EU) 1169/2011, Annex XIV, and marked `kcal_derived`.
- Cell parsing: `-` → missing, `traces` → 0, `< x` → x / 2.
- Spanish products described differently in France are approximated and noted in `review_note`.

## Canary Islands products
Checked in BEDCA on 2026-10-10:

| Product | In BEDCA | How it is represented |
|---|---|---|
| Gofio | ✅ «Gofio» | **(2026-10-12)** CIQUAL wholemeal wheat flour (approximation) until BEDCA is authorised |
| Mojo picón | ✅ «Mojo picón» | **(2026-10-12)** Recipe: oil + red pepper + vinegar + garlic + salt |
| Plátano | ✅ «Plátano» | CIQUAL banana (synonym: plátano de Canarias) |
| Queso majorero | ✅ «Queso majorero» | **(2026-10-12)** Approximation: CIQUAL dry (cured) goat cheese |
| Vieja | ✅ «Vieja, cruda» | **(2026-10-12)** Approximation: lean white fish (hake) |
| Papas arrugadas | ❌ | Recipe: «Patata, hervida» + salt (with its typical serving) |
| Queso palmero, cherne, almogrote | ❌ | Close equivalents marked as approximations (palmero: CIQUAL semi-dry goat cheese; cherne: white fish); almogrote left out |

## Columns
| Field | Origin |
|---|---|
| `id`, `name`, `category`, `state` (raw/cooked) | Target list |
| `source`, `source_id` | Script (traceability of every row) |
| Nutrients per 100 g of edible portion: kcal, protein, carbohydrates, sugars, fat, saturated fat, fibre, sodium | Official source, **literal value** |
| `salt_derived` | Calculated (sodium × 2.5), marked as derived |
| `allergens` (the 14 of EU regulation) | Rules by category + review |
| `synonyms` | Proposed by the assistant + author review |
| `servings` (1 slice of toast = 30 g, 1 plate = …) | Household measures from the sources + proposal + review |
| `section`, `shopping_format` | Proposal + review |

**(Implementation note, 2026-10-12)** Built table: [`data/foods.csv`](../data/foods.csv), with its [datasheet](../data/DATASHEET.md) and build report. Extra columns: `kcal_derived`, `source_name` (the source's own food name, for traceability), `max_portion_g` (largest realistic quantity, used by `verify_plan`) and `review_note`. `servings` and `shopping_format` are still pending (needed in milestone 3).

## Build steps
1. **Target list** of ~200 foods in Spanish, by category (includes the demo script's foods and the Canary products).
2. **Matching** with CIQUAL, choosing the code by hand among the candidates; BEDCA only for Spanish and Canary products missing in CIQUAL. Approximations are noted in `review_note`.
3. **Extraction** of nutrients per 100 g, literal, with their unit.
4. **Cross-source comparison** (when BEDCA is authorised): for foods present in BEDCA and CIQUAL, differences above 20 % in kcal are flagged. Automatic quality control (and a good table for the report).
5. **Own fields:** synonyms, allergens, servings, section, shopping format.
6. **Automatic validation** (also in CI): energy consistency (4·P + 4·C + 9·F + 2·fibre ≈ kcal, ±15 %, as a warning because source values are authoritative), plausible ranges, complete fields, unique ids, names and synonyms, source on every row.
7. **Author review** (30–60 min): flagged rows + a random sample.
8. **Datasheet** in the repository (`data/DATASHEET.md`): sources, licences, attribution, date, method, limitations.

## Household measures

Conversational measures have stable canonical ids in [`data/household_measure_definitions.csv`](../data/household_measure_definitions.csv):

| User expression | Canonical id | Nominal volume |
|---|---|---:|
| vaso, vasito | `vaso` | 200 ml |
| taza | `taza` | 250 ml |
| cucharada, cuchara sopera | `cucharada_sopera` | 15 ml |
| cucharadita, cuchara de café | `cucharadita` | 5 ml |
| plato, plato hondo, plato estándar | `plato` | food-specific |

Volume is only a conversational reference. Nutrient calculations use the food-specific grams in `household_measures.csv`, because density differs between foods. `plato` is provisional and only available for selected cooked foods and dishes; raw/cooked variants remain separate candidates when the difference matters.

The Coach should use an available measure without asking for grams, communicate the assumption briefly, and ask one question only when the food state or variant changes the result materially.

## How `search_food` searches
1. Normalises the text (lowercase, no accents, singular).
2. Exact match on names and synonyms.
3. If none, fuzzy search (typos).
4. Returns **several candidates with confidence**; if ambiguous, the agent **asks** («¿arroz blanco o integral?»).
5. If nothing is found: «not found». It **does not invent** nutrients. The agent asks the user or uses the barcode.

**(Implementation note, 2026-10-12)** [`tools/food_search.py`](../src/mojo_picon/tools/food_search.py):
- **Status** for the agent: `exact` (one food, exact name or synonym: use it), `approximate` (one candidate, partial or corrected: confirm), `ambiguous` (several: ask which one), `not_found` (never invent).
- **Confidence:** 1.0 exact name or synonym; 0.7 when the query words are contained in a food's name; × 0.9 when typos were corrected or filler words dropped. At most 5 candidates.
- With an exact match, alternatives are limited to the **same category** («arroz» → other rices; «tomate» does not bring «salsa de tomate»).
- **Plurals:** singular and plural forms of the table's words are mapped to each other («tomates», «nuez» → «nueces», «pechugas»).
- **Typos:** edit distance 1 for words of 4–7 letters, 2 for longer ones («platno» → plátano). Short words are not corrected, so «plato» is not read as «plátano».
- **Filler words** that are neither in the table nor a typo of a table word are dropped («un plato de arroz» → arroz). Mixed dishes not in the table («arroz con pollo») return `not_found`: the agent searches each food separately.
- **Close variants are not asked** (2026-10-16): with an exact match, if every alternative differs by **10 % or less in kcal per 100 g** (the tolerance `verify_plan` gives kcal), only the exact match is returned as `exact`. «salmón» → salmón al horno (205 vs crudo 194 kcal) without a question; «pollo» (pechuga 141 vs muslo 213) and «leche» (entera 65 vs desnatada 33) are still asked. Naming the variant («salmón crudo») always picks it.

## Limitations to document
- CIQUAL describes foods as sold in France; some Spanish products are approximations.
- BEDCA v1.0 dates from 2010; some products have changed.
- 200 foods do not cover everything: what is missing is asked about or looked up by barcode.
- Servings are indicative.
- Approximate equivalents (queso palmero, cherne) are marked as such.
