# JArchive

A toolset for scraping, searching, and playing Jeopardy! games from [J! Archive](https://j-archive.com).

## Workflow

```
scraper/parse_jarchive.py  →  output/season_XX/*.csv  →  game/jeopardy.py  →  jeopardy_game.html
                                                       →  search/ (CLI + web UI)
                                                       →  canon/build.py  →  canon_data.js + canon_map.html
```

Each program lives in its own directory (`scraper/`, `search/`, `game/`, `canon/`);
they all share the repo-root `output/` clue data, and generated artifacts
(`jeopardy_game.html`, `canon_data.js`, `canon_map.zip`, `canon_review.csv`,
`mention_cache.pkl`) land in the repo root. All paths are anchored to the repo
root, so the scripts work from any working directory.

## Scripts

### `scraper/parse_jarchive.py`

Scrapes J! Archive and saves game data as CSV files.

Configure `SEASONS_TO_PARSE` at the top of the file, then run it. For each season, it fetches all game IDs, parses each game's clues (Jeopardy, Double Jeopardy, and Final Jeopardy rounds), and writes one CSV per game to `output/season_<N>/YYYY-MM-DD.csv`. Already-downloaded games are skipped automatically.

Each CSV row contains: `category`, `value`, `round`, `question`, `answer`.

### `search/` — clue search (CLI + web UI)

Searches all downloaded CSV files for clues matching a term. `search_core.py`
holds the shared matching/scoring logic; `search.py` is the CLI and
`search_web.py` a local Flask UI (`py search/search_web.py`, opens the browser
automatically).

For the CLI, configure `SEARCH_TERM`, `SEARCH_MODE`, and `OUTPUT_MODE` at the top of the file. Two search modes are supported:

- `strict` — matches whole words only, ignoring punctuation
- `loose` — matches all terms anywhere in the text

Results are ranked by recency and dollar value. Output can go to stdout or be saved as a CSV file (`search_results_*.csv`).

### `game/jeopardy.py`

Generates a playable Jeopardy! game as a self-contained HTML file.

Configure `SEASONS` to control which seasons are eligible. Each run picks a random game from the downloaded CSVs, embeds the game data as JSON, and writes `jeopardy_game.html`, which opens automatically in the browser. The game supports score tracking, answer reveal, and correct/wrong/pass buttons.

### `canon/` — Jeopardy! Canon knowledge map

Builds a browsable, searchable study guide of the "Jeopardy canon" — the entities and
topics the show asks about again and again — from all downloaded CSVs. The goal is
*studying*: recency-weighted frequency (what the show asks **now** ranks first),
one-off trivia excluded, wordplay decomposed into its underlying facts.

```bash
python -m canon.build   # writes canon_data.js (~71 MB, gitignored), then open canon_map.html
```

Each build also writes `canon_map.zip` (gitignored) — `canon_map.html` +
`canon_data.js`, the complete set of files needed to view the map. Send that
zip to share the study guide; recipients unzip and open `canon_map.html`.

Rebuild any time; it is deterministic from `output/` + the `canon/data/` files and
takes ~3 min warm (~10 min cold, when `mention_cache.pkl` has to be rebuilt by NER). This section is the source of truth for how the pipeline works — **keep it
updated whenever the pipeline changes.**

#### Pipeline (Python 3.13; scikit-learn + spaCy)

1. **`canon/preprocess.py`** — loads every CSV into one clue table (date = filename).
   Normalizes answers into entity keys (lowercase, accents/punctuation stripped,
   leading article dropped, parentheticals split off as aliases). Merges aliases:
   parenthetical fuller forms (`"(Dwyane) Wade"` → `dwyane wade`), plurals (only when
   the plural is ≪ the singular — protects *Queens* the borough), and bare surnames
   into the unique frequent full name (`dali` → `salvador dali`) — but only when the
   full form is at least as common as the bare word, or primary entities get
   swallowed by incidental compounds (*australia* is not an alias of *western
   australia*; *mercury* is not Freddie Mercury). Pairs the guard can't prove
   safe but that are the same person live in the curated
   `canon/data/merge_overrides.json` (authoritative; ~150 entries:
   *ibsen* → *henrik ibsen*, *shakespeare* → *william shakespeare*, plus
   variant full forms like *js bach* → *johann sebastian bach*). Genuinely
   ambiguous surnames (*washington*, *columbus* the city, *bismarck*) stay
   separate entities. Skips pure-numeric answers.
2. **`canon/mentions.py`** — question-text mentions via **spaCy NER**
   (`en_core_web_sm`; PERSON/GPE/ORG/WORK_OF_ART… — never dates or numbers), minus
   `canon/data/stoplist.txt` (Clue Crew names, function words). This is how
   Shakespeare (81× answer, ~750× mentioned) gets his real weight. Results are
   cached in `mention_cache.pkl` (gitignored) keyed by question hash — a cold run
   over all 364k questions takes ~8 min, rebuilds are near-instant. Falls back to
   the old capitalized-run regex if spaCy is missing.
3. **`canon/entities.py`** — per entity: recency-weighted score
   `Σ exp(-λ·days_ago)`, answers full weight, mentions ×`MENTION_WEIGHT` (0.3);
   `HALF_LIFE_DAYS` = 6 years. Canon filter: ≥ 3 times an answer or ≥ 30 mentions.
   Trend label = last-5-years rate vs prior-10-years rate (rising/stable/declining).
   Tracks per-year answer *and* mention counts (`years`, `years_mention`).
   Display text prefers the answer spelling that matches the full canonical key
   (a merged entity shows "Henrik Ibsen" even though bare "Ibsen" is the more
   common answer text), falling back to the most common spelling.
4. **`canon/taxonomy.py`** + data — classifies category titles into a curated tree
   (`taxonomy.json`: 14 domains → ~87 topics). Precedence: `category_overrides.json`
   (manual tags, authoritative) → `exact` map → ordered `keywords` regexes
   (first match wins) applied to the *de-gimmicked* title (quotes stripped, so
   `"C"OUNTRIES` → COUNTRIES → geography). Title coverage ≈ 58% of clues.
   Entities get ≤ 2 topics by vote of their answer clues'
   topics — a topic needs ≥ 2 votes and ≥ 15% share, and **format topics never vote**
   (`FORMAT_TOPICS`: Before & After, Rhymes/Puns, Letter-Count, Stupid Answers,
   Hodgepodge — they describe a category's style, not a knowledge domain).
5. **`canon/clue_classifier.py`** — a **per-clue ML fallback** for the titles the
   rules can't place. Each build trains TF-IDF + logistic regression on the ~190k
   title-labeled clues (format topics excluded) and predicts topics for individual
   clues in unclassified categories; only predictions with confidence ≥ 0.6 stick.
   This is what splits grab-bags: FIRST THINGS FIRST's Bible clue, track clue, and
   Tudor clue each get their own topic. Lifts coverage ≈ 58% → ≈ 77%. Measured
   against noisy title labels it scores ~56%, but manual review of disagreements
   shows most are the model out-classifying a coarse title rule (real precision
   ~85%). The review worklist stays *title*-based, so manual tags — which beat ML
   fills — remain available.
6. **`canon/associations.py`** — "hear the cue, know the answer" pairs from two
   sources: descriptors after *"this …"* (`this canadian province` →
   Alberta/Ontario/BC) and proper-noun mentions (`mentions Puccini` → La bohème/
   Tosca/Madame Butterfly). Kept when seen ≥ 8× (mentions ≥ 10×) and the top 4
   answers cover ≥ 50%. Near-duplicates (clue-set containment > 0.6, e.g.
   *this verdi opera* ⊂ *mentions Verdi*) keep only the stronger cue.
7. **`canon/affixes.py`** — mines Greek/Latin **word-part families** from
   single-word answers against a curated affix list (~70 with meanings: neo-, geo-,
   arachno-, -ology, -phobia, -cracy…). Guards against false cognates via length
   floors (*neon* ≠ neo-) and per-affix blocklists (*George* ≠ geo-, *Romania* ≠
   -mania, *thesaurus* ≠ -saurus). Keeps words asked ≥ 2× and families with ≥ 3 words.
8. **`canon/build.py`** — orchestrates and serializes. Also: **manual-tagging loop**
   (reads `canon_review.csv` `topic` column → folds into `category_overrides.json` →
   rewrites the worklist with the top 400 still-unclassified categories + example
   clues) and **Before & After decomposition** — tries, in order: 2-way split at a
   shared word (*Wheel of Fortune cookie*), 3-way chain for BEFORE, DURING & AFTER
   triples, then a **disjoint** 2-way split for combos whose bridge isn't canon
   (*Glenn Miller [Light] Brigade* → glenn miller + light brigade). Each component
   entity is credited as a mention; emits the `before_after` building-blocks list.

#### `canon_data.js` schema (const `CANON_DATA`)

meta: `ref_date`, `half_life_days`, `mention_weight` (the UI recomputes
recency weights from these) · `clues` `[date, category, value, round, question,
answer]` · `clue_topics` (index into `topic_names`, per clue) · `taxonomy` domain→topics · `topics`
per-topic count + years · `entities` sorted by score desc:
`{k key, d display, al aliases, ac answer count, mc mention count, s score,
y years-as-answer, ym years-as-mention, t trend, tp topics, a answer clue idxs,
m mention clue idxs}` · `associations` `{cue, kind, n, s, ans:[{e entityIdx|null,
d, n}], c sample clue idxs}` · `before_after` `{e entityIdx, n half-count, x example
clue idxs}` · `affixes` `{x display ("geo-"/"-ology"), kind, m meaning, n total,
w:[{d display, n count, e entityIdx|null}]}`.

#### `canon_map.html` (UI, vanilla JS, works from `file://`)

Hash-routed views: **Browse** (domain cards → topic table → ranked entities with
trend badges), **topic pages** (year histogram; entities ranked by a **topic-local**
recency-weighted score — only the entity's clues filed under that topic count, with
in-topic answer/mention columns and a "Share" column showing how much of the
entity's canon lives there, so Chicago leads World Cities on its 38 city clues
instead of importing its 982 total appearances; computed client-side from
`clue_topics`, floor: ≥ 2 in-topic answers or ≥ 5 in-topic mentions; B&A page shows
the building-blocks table; format topics carry an explanatory note), **entity pages** (stat tiles,
stacked gold/blue answer+mention year chart, "cues that point here", As-answer /
Mentioned tabs with a show-hide answers toggle for self-quizzing, a text filter,
and **context chips** — clues grouped by their category's topic, so *Chicago*
separates into World Cities 31 / Theatre & Broadway 24 / Pop & Rock 18 (the band) /
Movies 13; chips appear when a name has ≥ 2 contexts of ≥ 3 clues or ≥ 10%),
**Power Associations** (filterable, expandable sample clues), **Word Parts**
(prefix/suffix tables with meanings; each word links to its entity page or a clue
search; filterable — try "fear"), **Clue Search** (raw substring over all 364K
clues). Global type-ahead search covers entity names + aliases + cues.

#### Tuning knobs (module constants)

`entities.py`: `HALF_LIFE_DAYS`, `MENTION_WEIGHT`, `MIN_ANSWER_COUNT`,
`MIN_MENTION_COUNT` · `associations.py`: `MIN_CUE_COUNT`, `MIN_MENTION_CUE_COUNT`,
`MIN_CONCENTRATION`, `MAX_OVERLAP`, `_GENERIC_CUES` · `taxonomy.py`:
`FORMAT_TOPICS` · `preprocess.py`: `SURNAME_MIN_COUNT`, `MENTION_ONLY_MIN_COUNT` ·
`affixes.py`: `AFFIXES`, `BLOCKLIST`, `MIN_WORD_COUNT`, `MIN_FAMILY_SIZE`,
`MAX_WORDS_PER_AFFIX` · `clue_classifier.py`: `MIN_CONFIDENCE`, `MAX_FEATURES` ·
`mentions.py`: `NER_LABELS`, `CACHE_FILE` (delete `mention_cache.pkl` to force a
full re-NER, e.g. after a spaCy model upgrade).

#### Known limitations / next ideas

- Same-name people in the *same* domain aren't split (the two George Bushes; bare
  *Roosevelt*); context chips only separate cross-domain senses. The per-entity clue
  filter is the workaround.
- The surname-merge frequency guard keeps a bare form more common than its full
  form as a separate entity (it's what protects *mercury* from Freddie Mercury).
  Known same-person splits are patched via `canon/data/merge_overrides.json` —
  add a `"bare key": "full key"` line and rebuild. Candidates were mined by
  comparing the two entities' answer-clue topic distributions (same-person pairs
  agree; mercury:Astronomy vs Freddie:Pop&Rock don't); left unmerged on purpose:
  *columbus*/*bismarck* (cities), *moses* (grandma), *pope* (alexander),
  *macbeth* (lady), *stanford*/*chrysler*/*heinz* (institution vs founder),
  *wayans*/*arquette* (multi-sibling).
- Clue coverage ~77% (58% from title rules + 19% from the per-clue ML fallback);
  grows via the `canon_review.csv` → overrides loop, new `category_map.json` rules
  (order matters; word-boundary the regexes), or lowering `MIN_CONFIDENCE`.
- ML-filled topics are ~85% right; the occasional clue lands in a sibling topic
  (or worse — a gems clue about *The Pearl Fishers* once went to Earth Science).
  Manual category tags always win over ML fills.
- `canon_data.js` is ~71 MB; if load ever hurts, cap clues per entity at serialization.
- Mention extraction is NER-based (`en_core_web_sm`): proper nouns and named
  works only — lowercase concepts ("photosynthesis") still don't register as
  mentions.

## Setup

Python 3.13 (interpreter at `%LOCALAPPDATA%\Programs\Python\Python313`).

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Output

Game CSVs are saved to `output/` (gitignored). The generated `jeopardy_game.html` is written to the project root.
