# Datasheet: food table (`foods.csv`)

## Purpose
Curated table of about 200 foods commonly eaten in Spain (including Canary Islands products), used by the deterministic tools: `search_food`, `get_nutrients`, `check_allergens`, `verify_plan` and the shopping list. Nutrient values are never typed by hand or produced by an LLM. See [`specs/food-table.md`](../specs/food-table.md).

## Files
| File | What it is | In git |
|---|---|---|
| `food_targets.csv` | Curated target list: id, Spanish name, category, source and source code, allergens, maximum realistic portion, supermarket section, synonyms, review notes | Yes |
| `build_foods.py` | Reproducible build script | Yes |
| `foods.csv` | The built table | Yes |
| `foods_report.md` | Build report: errors, warnings, derived values, approximations, pending rows | Yes |
| `fetch_bedca.py` | Downloads the BEDCA foods listed in `food_targets.csv` (`bedca_id`) from the official query interface | Yes |
| `raw/` | Downloaded source tables (CIQUAL Excel, BEDCA XML) | **No** (downloaded again to rebuild) |

## Sources and licences
| Source | Use | Licence and attribution |
|---|---|---|
| **CIQUAL 2020** (ANSES), English Excel table, 7 July 2020 | Main source | [Etalab Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/): reuse, including commercial, with attribution. *«Anses. 2020. Ciqual French food composition table.»* |
| **BEDCA** (AESAN), official XML query interface of bedca.net, downloaded 2026-10-12 | 6 Spanish and Canary products missing in CIQUAL (gofio, mojo picón, queso majorero, vieja, chorizo, paella) | Personal, educational or non-commercial use with attribution; values may not be modified; reproduction in electronic format requires AESAN's express authorisation. **Authorisation requested on 2026-10-12; used meanwhile as educational use while the repository is private.** Attribution: *«AESAN/BEDCA Base de Datos Española de Composición de Alimentos v1.0 (2010)»* |
| Recipes and approximations | Foods that are a combination of rows, or close equivalents | Computed from other rows of this table |

To rebuild, download the CIQUAL table to `data/raw/ciqual_2020_en.xls`:

```bash
curl -L -o data/raw/ciqual_2020_en.xls "https://ciqual.anses.fr/cms/sites/default/files/inline-files/Table%20Ciqual%202020_ENG_2020%2007%2007.xls"
uv run --group data python data/fetch_bedca.py   # BEDCA foods (cached in data/raw/bedca/)
uv run --group data python data/build_foods.py
```

> [!WARNING]
> **Publishing:** until AESAN authorises it, any public release (public repository, published dataset) must be built with `--no-bedca`, which replaces the BEDCA rows with their recipe or approximation.

File used for the current build: 3,632,640 bytes, SHA-256 `5551841f12f40fb6c869f80aa14e9db33bcfb7dcc135f000cb994a2cca4dc2f5`.

## Method
1. **Target list** curated by hand: Spanish name, category, CIQUAL code chosen among the candidates (the CIQUAL English name is kept in `source_name` for traceability; approximations are noted in `review_note`).
2. **Extraction** of nutrients per 100 g of edible portion from CIQUAL. Cell parsing rules:
   - `-` or empty → missing;
   - `traces` → 0;
   - `< x` → x / 2 (middle-bound convention).
3. **Energy:** CIQUAL's energy according to Regulation (EU) 1169/2011. When CIQUAL gives no energy value (38 foods in CIQUAL 2020, e.g. apple, lettuce, honey, nuts), it is **derived** from the macronutrients with the factors of that Regulation, Annex XIV (protein 4, carbohydrate 4, fat 9, fibre 2, polyols 2.4, alcohol 7, organic acids 3 kcal/g) and marked `kcal_derived = true`.
4. **Recipes** (`papas_arrugadas`, `cafe_con_leche`, `paella`, `mojo_picon`): weighted sum of other rows, in grams per 100 g of the finished dish, using cooked ingredients (so no yield factors are needed). Proportions are a proposal to be reviewed by the author.
5. **BEDCA rows:** values copied verbatim, only those expressed per 100 g of edible portion (`moex = W`); values in other bases (e.g. sodium of queso majorero, per kg) are left out instead of converted, and noted. `TR` (traces) without a number → 0. BEDCA gives energy only in kJ: kept in `energy_kj`, and `kcal = energy_kj / 4.184`. Each BEDCA row keeps its fallback (recipe or approximation) for `--no-bedca`, and the build report compares both.
6. **Approximations** (fallbacks, or foods missing everywhere): `chorizo`, `vieja` and `cherne` copy the closest row (marked in `source`); `gofio` (wholemeal wheat flour), `queso_majorero` (dry, cured goat cheese) and `queso_palmero` (semi-dry goat cheese) use the closest CIQUAL food directly (noted in `review_note`).
7. **Validation** (`mojo_picon.tools.foods.validate_rows`, also run by the test suite):
   - errors: duplicate ids, missing name, source or macronutrients, negative values, protein + carbs + fat above 100 g, energy above 905 kcal, unknown allergens, non-positive maximum portion, the same name or synonym in two foods (ignoring case and accents);
   - warnings (flagged for review): stated energy more than 15 % away from 4·P + 4·C + 9·F + 2·fibre; sugars above carbohydrates; saturated fat above fat.

## Own fields (to be reviewed by the author)
- **Allergens:** the 14 of Regulation (EU) 1169/2011, assigned by food type. Processed foods (muesli, surimi, cereal bars) vary by brand: noted in `review_note`.
- **Maximum realistic portion** (`max_portion_g`): used by `verify_plan` to reject unrealistic quantities.
- **Supermarket section** and **synonyms** (including Canary terms: papa, millo, bubango).
- **Pending columns:** household servings and shopping format (needed by the shopping list, milestone 3).

## Limitations
- CIQUAL describes foods as sold in France; some Spanish products are approximated (noted in `review_note`), e.g. queso fresco, queso curado, morcilla, salsa de tomate.
- Six Spanish and Canary products come from BEDCA pending AESAN's authorisation; without it, they fall back to recipes or approximations, which differ from BEDCA by −23 % to +66 % in kcal (see the build report). Queso palmero and cherne are approximations in any case.
- BEDCA's «Vieja, cruda» gives 4.9 g of carbohydrate, unusual for a raw fish; kept verbatim (values may not be modified). The downloaded BEDCA values were checked by the author against bedca.net on 2026-10-12 and match.
- Recipes stand for a typical home-made version; real dishes vary (a seafood paella and a Valencian paella differ).
- About 200 foods do not cover everything: what is missing is asked about or looked up by barcode.
- Energy derived from macronutrients is an estimate, close to but not identical to an analysed value.
