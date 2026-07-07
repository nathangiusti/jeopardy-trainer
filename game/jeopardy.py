#!/usr/bin/env python3
"""
Jeopardy Quiz App
Picks a random game from configured seasons and generates a playable HTML page.
"""

import csv
import json
import random
import webbrowser
from html import escape as html_escape
from pathlib import Path

# ============================================================
# CONFIGURATION  — edit these to customise
# ============================================================
SEASONS = list(range(35, 43))           # Seasons to pick from (35-42 inclusive)
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"        # Directory containing season CSV data
HTML_OUTPUT = REPO_ROOT / "jeopardy_game.html"  # Output HTML filename
# ============================================================


def get_all_games(seasons):
    games = []
    for season in seasons:
        season_dir = OUTPUT_DIR / f"season_{season}"
        if season_dir.exists():
            for csv_file in sorted(season_dir.glob("*.csv")):
                games.append(csv_file)
    return games


def load_game(csv_path):
    clues = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            clues.append({
                'category': row['category'].strip(),
                'value':    row['value'].strip(),
                'round':    row['round'].strip().lower(),
                'question': row['question'].strip(),
                'answer':   row['answer'].strip(),
            })
    return clues


def parse_value(v):
    try:
        return int(v.replace('$', '').replace(',', ''))
    except (ValueError, AttributeError):
        return 0


def organize_board(clues):
    def build_round(round_clues):
        seen = set()
        cats_ordered = []
        for c in round_clues:
            if c['category'] not in seen:
                seen.add(c['category'])
                cats_ordered.append(c['category'])
        result = []
        for cat in cats_ordered:
            cat_clues = sorted(
                [c for c in round_clues if c['category'] == cat],
                key=lambda x: parse_value(x['value'])
            )
            result.append({'category': cat, 'clues': cat_clues})
        return result

    return {
        'jeopardy':       build_round([c for c in clues if c['round'] == 'jeopardy']),
        'double_jeopardy': build_round([c for c in clues if c['round'] == 'double jeopardy']),
        'final':          [c for c in clues if c['round'] == 'final'],
    }


# ---------------------------------------------------------------------------
# HTML template — uses PLACEHOLDER_GAME_NAME and PLACEHOLDER_GAME_JSON
# so no f-string / curly-brace escaping is needed
# ---------------------------------------------------------------------------
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Jeopardy! — PLACEHOLDER_GAME_NAME</title>
<style>
:root {
  --blue:        #060ce9;
  --dark-blue:   #000080;
  --deeper-blue: #00004e;
  --gold:        #ffcc00;
  --white:       #ffffff;
  --bg:          #010118;
  --answered-bg: #111130;
  --correct:     #1a6b1a;
  --wrong:       #8b0000;
  --passed:      #444;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--white);
  font-family: Georgia, 'Times New Roman', serif;
  min-height: 100vh;
}

/* ── Scoreboard ─────────────────────────────────────────── */
#scoreboard {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--deeper-blue);
  border-bottom: 3px solid var(--gold);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

#scoreboard .app-title {
  font-size: 1.5em;
  font-weight: bold;
  color: var(--gold);
  letter-spacing: 3px;
  text-shadow: 2px 2px 6px rgba(0,0,0,0.9);
  white-space: nowrap;
}

#scoreboard .stats {
  display: flex;
  gap: 18px;
  align-items: center;
  flex-wrap: wrap;
}

.stat-box { text-align: center; min-width: 72px; }

.stat-label {
  font-size: 0.6em;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #99bbff;
}

.stat-value {
  font-size: 1.4em;
  font-weight: bold;
}

#score-val  { color: var(--gold); }
#right-val  { color: #66ff66; }
#wrong-val  { color: #ff6666; }
#passed-val { color: #ffaa44; }

#scoreboard .game-label {
  font-size: 0.75em;
  color: #99bbff;
  text-align: right;
  flex-shrink: 0;
}

/* ── Game sections ───────────────────────────────────────── */
.game-section { padding: 20px 12px 10px; }

.section-title {
  text-align: center;
  font-size: 2em;
  font-weight: bold;
  color: var(--gold);
  letter-spacing: 5px;
  text-transform: uppercase;
  text-shadow: 3px 3px 8px rgba(0,0,0,0.9);
  margin-bottom: 14px;
  padding: 14px;
  border: 3px solid var(--gold);
  border-radius: 4px;
  background: rgba(6,12,233,0.18);
}

/* ── Board grid ──────────────────────────────────────────── */
.board-grid {
  display: grid;
  gap: 4px;
  width: 100%;
}

.cat-header {
  background: var(--blue);
  border: 2px solid #2233bb;
  padding: 10px 6px;
  text-align: center;
  font-size: 0.82em;
  font-weight: bold;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--white);
  min-height: 66px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  word-break: break-word;
  line-height: 1.35;
}

.clue-cell {
  background: var(--blue);
  border: 2px solid #2233bb;
  border-radius: 3px;
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.12s, transform 0.1s, border-color 0.12s;
  user-select: none;
}

.clue-cell:hover:not(.answered) {
  background: #1a2fff;
  transform: scale(1.03);
  border-color: var(--gold);
}

.clue-cell.answered {
  background: var(--answered-bg);
  cursor: default;
  border-color: #1a1a3a;
}

.clue-cell.answered .cell-value { opacity: 0.12; }

.clue-cell.res-correct { background: var(--correct) !important; border-color: #33aa33 !important; }
.clue-cell.res-wrong   { background: var(--wrong)   !important; border-color: #cc3333 !important; }
.clue-cell.res-passed  { background: var(--passed)  !important; border-color: #666    !important; }

.cell-value {
  font-size: 1.7em;
  font-weight: bold;
  color: var(--gold);
  text-shadow: 2px 2px 5px rgba(0,0,0,0.8);
  pointer-events: none;
}

/* ── Final Jeopardy card ─────────────────────────────────── */
.final-card {
  background: var(--blue);
  border: 3px solid var(--gold);
  border-radius: 8px;
  padding: 36px 30px;
  text-align: center;
  cursor: pointer;
  transition: background 0.12s;
  max-width: 560px;
  margin: 0 auto 30px;
  user-select: none;
}

.final-card:hover:not(.answered) { background: #1a2fff; }

.final-card.answered {
  background: var(--answered-bg);
  border-color: #33aaff;
  cursor: default;
}

.final-cat {
  font-size: 1.3em;
  font-weight: bold;
  color: var(--gold);
  text-transform: uppercase;
  letter-spacing: 3px;
  margin-bottom: 14px;
}

.final-prompt { color: #99bbff; font-style: italic; font-size: 0.9em; }

/* ── Modal ───────────────────────────────────────────────── */
#modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.88);
  z-index: 200;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

#modal-overlay.open { display: flex; }

#modal {
  background: var(--blue);
  border: 4px solid var(--gold);
  border-radius: 10px;
  padding: 34px 30px 28px;
  max-width: 680px;
  width: 100%;
  max-height: 90vh;
  overflow-y: auto;
  text-align: center;
  box-shadow: 0 10px 50px rgba(0,0,0,0.95);
}

.modal-category {
  font-size: 1.05em;
  color: var(--gold);
  text-transform: uppercase;
  letter-spacing: 3px;
  font-weight: bold;
  margin-bottom: 6px;
}

.modal-value {
  font-size: 2.1em;
  color: var(--gold);
  font-weight: bold;
  text-shadow: 2px 2px 6px rgba(0,0,0,0.8);
  margin-bottom: 22px;
}

.modal-question {
  font-size: 1.22em;
  line-height: 1.65;
  color: var(--white);
  margin-bottom: 22px;
  padding: 18px 16px;
  background: rgba(0,0,0,0.35);
  border-radius: 6px;
}

.modal-answer-wrap {
  overflow: hidden;
  max-height: 0;
  transition: max-height 0.35s ease, opacity 0.3s ease;
  opacity: 0;
  margin-bottom: 0;
}

.modal-answer-wrap.visible {
  max-height: 200px;
  opacity: 1;
  margin-bottom: 20px;
}

.modal-answer {
  font-size: 1.25em;
  font-weight: bold;
  color: var(--gold);
  padding: 16px;
  background: rgba(0,0,0,0.45);
  border-radius: 6px;
  border: 2px solid var(--gold);
}

/* Buttons */
.btn {
  padding: 13px 22px;
  border: none;
  border-radius: 6px;
  font-size: 1em;
  font-weight: bold;
  cursor: pointer;
  letter-spacing: 1px;
  text-transform: uppercase;
  transition: opacity 0.15s, transform 0.1s;
  font-family: inherit;
}

.btn:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
.btn:active:not(:disabled) { transform: translateY(0); }
.btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }

.btn-reveal {
  background: var(--gold);
  color: #000;
  width: 100%;
  margin-bottom: 16px;
  font-size: 1.05em;
  padding: 15px;
}

.action-buttons {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}

.btn-correct { background: #22aa22; color: var(--white); flex: 1; min-width: 110px; }
.btn-wrong   { background: #cc2222; color: var(--white); flex: 1; min-width: 110px; }
.btn-pass    { background: #666;    color: var(--white); flex: 1; min-width: 110px; }

/* ── Responsive ─────────────────────────────────────────── */
@media (max-width: 720px) {
  .section-title { font-size: 1.5em; letter-spacing: 2px; }
  .cell-value { font-size: 1.2em; }
  #scoreboard .app-title { font-size: 1.1em; }
}

@media (max-width: 500px) {
  .cell-value { font-size: 0.95em; }
  .modal-question { font-size: 1.05em; }
}
</style>
</head>
<body>

<!-- ── Scoreboard ── -->
<div id="scoreboard">
  <div class="app-title">JEOPARDY!</div>
  <div class="stats">
    <div class="stat-box">
      <div class="stat-label">Score</div>
      <div class="stat-value" id="score-val">$0</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Correct</div>
      <div class="stat-value" id="right-val">0</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Wrong</div>
      <div class="stat-value" id="wrong-val">0</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Passed</div>
      <div class="stat-value" id="passed-val">0</div>
    </div>
  </div>
  <div class="game-label">PLACEHOLDER_GAME_NAME</div>
</div>

<!-- ── Board ── -->
<div id="game-container"></div>

<!-- ── Modal ── -->
<div id="modal-overlay">
  <div id="modal">
    <div class="modal-category" id="modal-cat"></div>
    <div class="modal-value"    id="modal-val"></div>
    <div class="modal-question" id="modal-q"></div>
    <div class="modal-answer-wrap" id="modal-ans-wrap">
      <div class="modal-answer" id="modal-ans"></div>
    </div>
    <button class="btn btn-reveal" id="btn-reveal" onclick="revealAnswer()">&#128065; Reveal Answer</button>
    <div class="action-buttons" id="action-btns">
      <button class="btn btn-correct" id="btn-correct" onclick="record('correct')" disabled>&#10003; Correct</button>
      <button class="btn btn-wrong"   id="btn-wrong"   onclick="record('wrong')"   disabled>&#10007; Wrong</button>
      <button class="btn btn-pass"    id="btn-pass"    onclick="record('pass')"    disabled>&#8594; Pass</button>
    </div>
  </div>
</div>

<script>
// ── Game data ────────────────────────────────────────────────────────────────
const GAME = PLACEHOLDER_GAME_JSON;

// ── State ────────────────────────────────────────────────────────────────────
let score = 0, numRight = 0, numWrong = 0, numPassed = 0;
let current = null;   // { roundKey, catIdx, clueIdx, value }
const answered = {};  // cellKey -> 'correct' | 'wrong' | 'pass'

// ── Helpers ──────────────────────────────────────────────────────────────────
function cellKey(rk, ci, qi) { return rk + '-' + ci + '-' + qi; }

function parseVal(v) {
  if (!v) return 0;
  return parseInt(v.replace(/[$,]/g, ''), 10) || 0;
}

function fmtScore(n) {
  const sign = n < 0 ? '-' : '';
  return sign + '$' + Math.abs(n).toLocaleString();
}

function updateBoard() {
  document.getElementById('score-val').textContent  = fmtScore(score);
  document.getElementById('right-val').textContent  = numRight;
  document.getElementById('wrong-val').textContent  = numWrong;
  document.getElementById('passed-val').textContent = numPassed;
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openClue(roundKey, catIdx, clueIdx) {
  const key = cellKey(roundKey, catIdx, clueIdx);
  if (answered[key]) return;

  let clue;
  if (roundKey === 'final') {
    clue = GAME.final[0];
  } else {
    clue = GAME[roundKey][catIdx].clues[clueIdx];
  }

  const val = parseVal(clue.value);
  current = { roundKey, catIdx, clueIdx, value: val };

  document.getElementById('modal-cat').textContent = clue.category;
  document.getElementById('modal-val').textContent = clue.value || 'FINAL JEOPARDY!';
  document.getElementById('modal-q').textContent   = clue.question;
  document.getElementById('modal-ans').textContent = 'Answer: ' + clue.answer;

  // Reset answer reveal
  document.getElementById('modal-ans-wrap').classList.remove('visible');
  document.getElementById('btn-reveal').disabled   = false;
  document.getElementById('btn-reveal').style.display = 'block';
  document.getElementById('btn-correct').disabled  = true;
  document.getElementById('btn-wrong').disabled    = true;
  document.getElementById('btn-pass').disabled     = true;

  document.getElementById('modal-overlay').classList.add('open');
}

function revealAnswer() {
  document.getElementById('modal-ans-wrap').classList.add('visible');
  document.getElementById('btn-reveal').style.display = 'none';
  document.getElementById('btn-correct').disabled = false;
  document.getElementById('btn-wrong').disabled   = false;
  document.getElementById('btn-pass').disabled    = false;
}

function record(result) {
  if (!current) return;
  const { roundKey, catIdx, clueIdx, value } = current;
  const key = cellKey(roundKey, catIdx, clueIdx);

  if (result === 'correct') { score += value; numRight++; }
  else if (result === 'wrong') { score -= value; numWrong++; }
  else { numPassed++; }

  answered[key] = result;
  updateBoard();

  // Update cell appearance
  const cell = document.getElementById('cell-' + key);
  if (cell) {
    cell.classList.add('answered', 'res-' + result);
  }

  closeModal();
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  current = null;
}

// Close on overlay backdrop click or Escape key
document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay')) closeModal();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Board builder ─────────────────────────────────────────────────────────────
function buildRoundSection(roundKey, title) {
  const section = document.createElement('div');
  section.className = 'game-section';

  const heading = document.createElement('div');
  heading.className = 'section-title';
  heading.textContent = title;
  section.appendChild(heading);

  const round = GAME[roundKey];
  if (!round || round.length === 0) {
    const msg = document.createElement('p');
    msg.style.cssText = 'text-align:center;color:#888;padding:30px;';
    msg.textContent = 'No clues available for this round.';
    section.appendChild(msg);
    return section;
  }

  const numCols = round.length;
  const numRows = Math.max(...round.map(c => c.clues.length));

  const grid = document.createElement('div');
  grid.className = 'board-grid';
  grid.style.gridTemplateColumns = `repeat(${numCols}, 1fr)`;

  // Category headers (row 0)
  round.forEach(cat => {
    const h = document.createElement('div');
    h.className = 'cat-header';
    h.textContent = cat.category;
    grid.appendChild(h);
  });

  // Clue rows
  for (let row = 0; row < numRows; row++) {
    for (let col = 0; col < numCols; col++) {
      const clue = round[col].clues[row];
      const cell = document.createElement('div');

      if (clue) {
        const key = cellKey(roundKey, col, row);
        cell.className = 'clue-cell';
        cell.id = 'cell-' + key;

        const vEl = document.createElement('div');
        vEl.className = 'cell-value';
        vEl.textContent = clue.value || '?';
        cell.appendChild(vEl);

        cell.addEventListener('click', () => openClue(roundKey, col, row));
      } else {
        // Missing clue (some games have fewer clues per category)
        cell.className = 'clue-cell answered';
        cell.style.opacity = '0.25';
      }
      grid.appendChild(cell);
    }
  }

  section.appendChild(grid);
  return section;
}

function buildFinalSection() {
  const section = document.createElement('div');
  section.className = 'game-section';

  const heading = document.createElement('div');
  heading.className = 'section-title';
  heading.textContent = 'Final Jeopardy!';
  section.appendChild(heading);

  const finals = GAME.final;
  if (!finals || finals.length === 0) {
    const msg = document.createElement('p');
    msg.style.cssText = 'text-align:center;color:#888;padding:30px;';
    msg.textContent = 'No Final Jeopardy clue available.';
    section.appendChild(msg);
    return section;
  }

  const clue = finals[0];
  const key  = cellKey('final', 0, 0);

  const card = document.createElement('div');
  card.className = 'final-card';
  card.id = 'cell-' + key;

  const catEl = document.createElement('div');
  catEl.className = 'final-cat';
  catEl.textContent = clue.category;
  card.appendChild(catEl);

  const prompt = document.createElement('div');
  prompt.className = 'final-prompt';
  prompt.textContent = 'Click to play Final Jeopardy';
  card.appendChild(prompt);

  card.addEventListener('click', () => openClue('final', 0, 0));
  section.appendChild(card);
  return section;
}

// ── Init ──────────────────────────────────────────────────────────────────────
const container = document.getElementById('game-container');
container.appendChild(buildRoundSection('jeopardy',        'Jeopardy!'));
container.appendChild(buildRoundSection('double_jeopardy', 'Double Jeopardy!'));
container.appendChild(buildFinalSection());
updateBoard();
</script>
</body>
</html>'''


def main():
    all_games = get_all_games(SEASONS)
    if not all_games:
        print(f"ERROR: No game CSV files found in '{OUTPUT_DIR}' for seasons {SEASONS}.")
        print("Make sure the 'output/' directory exists and contains season_XX subdirectories.")
        return

    chosen    = random.choice(all_games)
    game_date = chosen.stem                                         # e.g. "2019-03-15"
    season    = chosen.parent.name.replace('_', ' ').title()       # e.g. "Season 42"
    game_name = f"{game_date}  ({season})"

    print(f"Selected game : {chosen.parent.name}/{chosen.name}")

    clues = load_game(chosen)
    board = organize_board(clues)

    j_cats  = len(board['jeopardy'])
    dj_cats = len(board['double_jeopardy'])
    fin     = len(board['final'])
    print(f"Loaded        : {j_cats} J categories, {dj_cats} DJ categories, {fin} Final clue(s)")

    # Safely embed JSON in a <script> tag (escape </script> closing sequence)
    game_json = json.dumps(board, ensure_ascii=False)
    game_json = game_json.replace('</', '<\\/')

    html = HTML_TEMPLATE
    html = html.replace('PLACEHOLDER_GAME_NAME', html_escape(game_name))
    html = html.replace('PLACEHOLDER_GAME_JSON', game_json)

    HTML_OUTPUT.write_text(html, encoding='utf-8')
    print(f"HTML written  : {HTML_OUTPUT.resolve()}")

    uri = HTML_OUTPUT.resolve().as_uri()
    print(f"Opening       : {uri}")
    webbrowser.open(uri)


if __name__ == '__main__':
    main()
