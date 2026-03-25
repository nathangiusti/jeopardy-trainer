# JArchive

A toolset for scraping, searching, and playing Jeopardy! games from [J! Archive](https://j-archive.com).

## Workflow

```
parse_jarchive.py  →  output/season_XX/*.csv  →  jeopardy.py  →  jeopardy_game.html
                                               →  search.py
```

## Scripts

### `parse_jarchive.py`

Scrapes J! Archive and saves game data as CSV files.

Configure `SEASONS_TO_PARSE` at the top of the file, then run it. For each season, it fetches all game IDs, parses each game's clues (Jeopardy, Double Jeopardy, and Final Jeopardy rounds), and writes one CSV per game to `output/season_<N>/YYYY-MM-DD.csv`. Already-downloaded games are skipped automatically.

Each CSV row contains: `category`, `value`, `round`, `question`, `answer`.

### `search.py`

Searches all downloaded CSV files for clues matching a term.

Configure `SEARCH_TERM`, `SEARCH_MODE`, and `OUTPUT_MODE` at the top of the file. Two search modes are supported:

- `strict` — matches whole words only, ignoring punctuation
- `loose` — matches all terms anywhere in the text

Results are ranked by recency and dollar value. Output can go to stdout or be saved as a CSV file (`search_results_*.csv`).

### `jeopardy.py`

Generates a playable Jeopardy! game as a self-contained HTML file.

Configure `SEASONS` to control which seasons are eligible. Each run picks a random game from the downloaded CSVs, embeds the game data as JSON, and writes `jeopardy_game.html`, which opens automatically in the browser. The game supports score tracking, answer reveal, and correct/wrong/pass buttons.

## Setup

```bash
pip install requests beautifulsoup4
```

## Output

Game CSVs are saved to `output/` (gitignored). The generated `jeopardy_game.html` is written to the project root.
