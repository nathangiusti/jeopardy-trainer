import re
import threading
import webbrowser

from flask import Flask, request
from markupsafe import Markup, escape

from search_core import OUTPUT_DIR, search_clues, calculate_scores

app = Flask(__name__)

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>J! Archive Search</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Arial', sans-serif;
    background: #0a0a1a;
    color: #e0e0e0;
    min-height: 100vh;
    padding: 24px 16px;
  }

  header {
    text-align: center;
    margin-bottom: 28px;
  }

  header h1 {
    font-size: 2.2rem;
    color: #f5c518;
    letter-spacing: 2px;
    text-shadow: 0 0 20px rgba(245,197,24,0.3);
  }

  header p {
    color: #888;
    font-size: 0.85rem;
    margin-top: 4px;
  }

  .search-form {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 28px;
  }

  .search-form input[type=text] {
    padding: 10px 14px;
    font-size: 16px;
    border-radius: 6px;
    border: 2px solid #333;
    background: #1a1a2e;
    color: #fff;
    width: 320px;
    outline: none;
    transition: border-color 0.2s;
  }

  .search-form input[type=text]:focus {
    border-color: #f5c518;
  }

  .search-form select {
    padding: 10px 12px;
    font-size: 14px;
    border-radius: 6px;
    border: 2px solid #333;
    background: #1a1a2e;
    color: #ccc;
    outline: none;
    cursor: pointer;
  }

  .search-form button {
    padding: 10px 24px;
    font-size: 15px;
    font-weight: bold;
    background: #f5c518;
    color: #000;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.2s, transform 0.1s;
  }

  .search-form button:hover { background: #e6b800; }
  .search-form button:active { transform: scale(0.97); }

  .summary {
    text-align: center;
    margin-bottom: 20px;
  }

  .scores {
    font-size: 1.1rem;
    color: #f5c518;
    margin-bottom: 4px;
  }

  .result-count {
    font-size: 0.85rem;
    color: #888;
  }

  .clue {
    background: #111827;
    border: 1px solid #1f2937;
    border-left: 4px solid #f5c518;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 10px auto;
    max-width: 860px;
    transition: border-left-color 0.2s;
  }

  .clue:hover {
    border-left-color: #e6b800;
  }

  .clue-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
  }

  .category {
    color: #6b7280;
    font-size: 0.8rem;
  }

  .meta {
    color: #6b7280;
    font-size: 0.8rem;
  }

  .meta .value {
    color: #4ade80;
    font-weight: bold;
  }

  .field {
    margin-top: 10px;
  }

  .label {
    font-size: 0.7rem;
    font-weight: bold;
    color: #4b5563;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 3px;
  }

  .text {
    color: #f9fafb;
    font-size: 1.05rem;
    line-height: 1.6;
  }

  mark {
    background: #f5c518;
    color: #000;
    padding: 0 2px;
    border-radius: 3px;
    font-weight: bold;
  }

  .no-results {
    text-align: center;
    color: #6b7280;
    margin-top: 60px;
    font-size: 1.1rem;
  }
</style>
</head>
<body>

<header>
  <h1>J! Archive Search</h1>
  <p>Search Jeopardy! clues and answers</p>
</header>

<form class="search-form" method="get" action="/">
  <input type="text" name="q" placeholder="Enter search term…" value="{{ query }}" autofocus>
  <select name="mode">
    <option value="strict" {{ 'selected' if mode == 'strict' }}>Strict (whole word)</option>
    <option value="loose" {{ 'selected' if mode == 'loose' }}>Loose (substring)</option>
  </select>
  <button type="submit">Search</button>
</form>

{% if query %}
  {% if results %}
    <div class="summary">
      <div class="scores">Frequency: {{ "%.2f"|format(frequency_score) }} &nbsp;|&nbsp; Value: {{ "%.2f"|format(value_score) }}</div>
      <div class="result-count">{{ results|length }} clue{{ 's' if results|length != 1 }} found for <em>"{{ query }}"</em></div>
    </div>

    {% for r in results %}
    <div class="clue">
      <div class="clue-header">
        <span class="category">{{ r.category }}</span>
        <span class="meta">
          Season {{ r.season }} &nbsp;·&nbsp; {{ r.date }} &nbsp;·&nbsp; {{ r.round }}
          &nbsp;·&nbsp; <span class="value">{{ r.value or 'Final Jeopardy' }}</span>
        </span>
      </div>
      <div class="field">
        <div class="label">Clue</div>
        <div class="text">{{ r.question_hl }}</div>
      </div>
      <div class="field">
        <div class="label">Answer</div>
        <div class="text">{{ r.answer_hl }}</div>
      </div>
    </div>
    {% endfor %}

  {% else %}
    <div class="no-results">No results found for <em>"{{ query }}"</em></div>
  {% endif %}
{% endif %}

</body>
</html>
"""


def highlight(text: str, search_term: str, mode: str) -> Markup:
    """Escape text for HTML, then wrap matching terms in <mark> tags."""
    if not text:
        return Markup('')
    safe = str(escape(text))
    if mode == "strict":
        pattern = re.compile(
            r'(?<![a-zA-Z])(' + re.escape(search_term) + r')(?![a-zA-Z])',
            re.IGNORECASE
        )
    else:
        terms = [re.escape(t) for t in search_term.split() if t]
        if not terms:
            return Markup(safe)
        pattern = re.compile(r'(' + '|'.join(terms) + r')', re.IGNORECASE)
    return Markup(pattern.sub(r'<mark>\1</mark>', safe))


@app.route('/')
def index():
    from flask import render_template_string
    query = request.args.get('q', '').strip()
    mode = request.args.get('mode', 'strict')
    if mode not in ('strict', 'loose'):
        mode = 'strict'

    results = []
    frequency_score = 0.0
    value_score = 0.0

    if query:
        results = search_clues(query, OUTPUT_DIR, mode)
        frequency_score, value_score = calculate_scores(results)
        for r in results:
            r['question_hl'] = highlight(r['question'], query, mode)
            r['answer_hl'] = highlight(r['answer'], query, mode)

    return render_template_string(
        TEMPLATE,
        query=query,
        mode=mode,
        results=results,
        frequency_score=frequency_score,
        value_score=value_score,
    )


if __name__ == '__main__':
    threading.Timer(0.6, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(debug=False)