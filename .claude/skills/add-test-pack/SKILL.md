---
name: add-test-pack
description: Add questions or full tests (ORT, SAT, CSCA, ЕГЭ, ЕНТ, ОГЭ) to Monday as a content pack in monday/data/packs. Use whenever the user wants to add a test, a variant, a book's questions or a question set, or asks how a test of some format is put together.
---

# Adding a test / question pack to Monday

Ready-made content is shipped as **content packs**: `monday/data/packs/<pack_id>.json`
(+ optional `monday/data/packs/<pack_id>/figures/*.png`). On start-up `monday/packs.py`
(`ensure_packs`) imports every pack the database hasn't seen, so a pushed pack appears on
Render after deploy. Read `monday/packs.py` before starting; it is short and is the source of truth.

## Rules that bite

- **A pack is imported once per database** (AppMeta key `pack:<pack_id>`). Editing a pack that is
  already live changes nothing on Render. To add more: create a **new pack file** (e.g. `<pack>_p2.json`)
  — a collection may borrow question ids from other packs (`_foreign_questions`). To fix live data,
  add a one-time fix in `monday/cleanup.py` (`_once(...)`).
- Pack ids ≤ ~34 chars (the AppMeta key is cut to 40). Question ids must be unique across all packs.
- Every `skill` must be an existing master-map code from `MASTER` in `monday/taxonomy.py`. List them:
  `venv/bin/python -c "from monday.taxonomy import MASTER; [print(c, '-', n, e) for _,_,s in MASTER for _,_,k in s for c,n,e,_ in k]"`
- Check every answer against the source key **and** solve it; leave out items with a wrong key or an
  ambiguous statement, and say which ones in the commit message.
- Text is plain text with `$…$` LaTeX. No HTML: `<br>` is shown literally (bug seen in ORT q31) —
  use `\n` for line breaks or put list items (I, II, III) in separate lines.
- The collection's time is `minutes_per_module` (× 2 when `module_split` is set). The `minutes` key is
  only informational.
- Don't push to GitHub/Render without asking the user.

## Pack file

```json
{
  "id": "<pack_id>", "title": "…", "exam": "ORT|SAT|CSCA|EGE|ENT|OGE", "language": "ru|en",
  "questions": [ { …question… } ],
  "collections": [ { …collection… } ]
}
```

### Question

| key | meaning |
|---|---|
| `id` | unique, e.g. `ortmb26_t01_c02` (pack prefix + where it came from) |
| `text` | statement, `$…$` LaTeX |
| `answer_type` | `choice` · `number` · `written` |
| `options` | for `choice`: list of option texts (no letters — the page adds А/Б/В… or A/B/C…); `[]` otherwise |
| `correct` | `choice`: index as string (`"0"` = first option). `number`: value, several accepted ones joined with `\|` (`"2/3\|0.666\|0.667"`). `written`: reference answer text |
| `explanation` | worked solution shown on the results page |
| `skill` | master-map code (see above) |
| `difficulty` | 1–3 |
| `exams`, `language` | optional; default to the pack's |
| `material` | optional reading blocks; ORT comparison: `[{"type": "columns", "left_title": "Колонка А", "left": "$a+b$", "right_title": "Колонка Б", "right": "$a+c$"}]` |
| `image` | optional `figures/<file>.png` inside the pack folder |
| `weight`, `rubric` | `written` only (ЕГЭ part 2): max points and `[{"points": 2, "text": "…"}, …]` |
| `tags`, `source` | free; `source` = `{"book": "…", "where": "тема 1, №2"}` |

### Collection (a test students can start)

```json
{"id": "ortmb26_v1", "title": "ОРТ Математика · Вариант 1 (Monday)", "description": "…",
 "format": "ort", "category": "full", "calculator": false, "minutes_per_module": 90,
 "questions": ["<question id>", "…"]}
```

`format` decides how the test page looks (`TEST_FORMATS` in `monday/constants.py`,
`build_layout` in `monday/services.py`, template `monday/templates/student/attempt.html`).
`category`: `full` (whole variant) or `thematic`.

## Per exam

- **ORT** (`format: "ort"`, pages + bubble answer sheet, one correction per answer). Math variant = 60
  questions, 90 min, one module: **1–30 comparisons** — `choice` with exactly these 4 options in this order
  `["Величина А больше", "Величина Б больше", "Величины равны", "Недостаточно данных"]`, a `columns`
  material, text ending «Сравните величины в колонках А и Б.»; **31–60** five options (А–Д).
  Keep that order: the page detects the leading comparison block and shows it as part 1 (one key,
  compact cards, sheet 1–30), the rest as part 2 (sheet 31–60). Example: `ort_monday_book_2026.json`.
- **SAT** (`format: "sat"`, grid, Desmos, two modules with locked answers): 44 questions,
  `"module_split": 22`, `"minutes_per_module": 35`, `"calculator": true`, English. `choice` (4 options)
  and `number` (student-produced: accepted forms like `"7/2|3.5"`). Example: `princeton_dsat_2025.json`.
- **CSCA** (`format: "csca"`): 48 `choice` questions, 60 min, English, `"calculator": false`.
  Example: `csca_official_2026.json`.
- **ЕГЭ** (`format: "ege"`): part 1 = 12 `number` questions; part 2 = 7 `written` with `weight` + `rubric`
  (student uploads a photo, self-check / teacher mark). Full variant = 19 questions, 235 min; it may
  borrow part-1 ids from another pack. Examples: `ege_yaschenko_2026.json`, `ege_yaschenko_2026_p2.json`.
- **ЕНТ / ОГЭ** (`format: "ent"` / `"oge"`, grid): no pack yet. Use `choice` / `number` like the others;
  check the real exam structure (count, time, option count) with the user before writing.

## Checklist

1. Write the pack JSON (a small Python script in the scratchpad that builds it is easier to check than hand-written JSON).
2. Validate: every `skill` exists; `choice` → `0 <= int(correct) < len(options)` and options unique;
   `number` → `parse_number(correct)` (from `monday.services`) parses every `|`-part; every collection id exists.
3. Add a test in `tests/test_app.py` (pattern: `test_sat_pack_is_imported_with_two_35_minute_modules`,
   `test_ort_math_in_two_parts`): the works exist with the right layout/count, a start + hand-in works.
4. `venv/bin/python -m pytest -q tests/test_app.py`.
5. Look at the test page in a browser with a throwaway DB, e.g. a `.claude/launch.json` entry running
   `DATABASE_URL=sqlite:///<scratchpad>/check.db PORT=5077 MONDAY_DEBUG=0 venv/bin/python app.py`
   (log in as the seed student `student@monday.kg`); restart it after template changes.
6. Commit with a message listing source, counts, timing and any items left out; ask before pushing.
