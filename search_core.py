import csv
import os
import math
import re
import string
from datetime import datetime, date

OUTPUT_DIR = "output"
RECENCY_DECAY_RATE = 0.001
FINAL_JEOPARDY_VALUE = 4000


def parse_value(value_str: str) -> int:
    if not value_str:
        return FINAL_JEOPARDY_VALUE
    return int(value_str.replace('$', '').replace(',', ''))


def days_since(date_str: str) -> int:
    try:
        game_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        return (date.today() - game_date).days
    except:
        return 365 * 5


def strip_punctuation(text: str) -> str:
    return text.translate(str.maketrans('', '', string.punctuation))


def matches_strict(text: str, pattern: re.Pattern) -> bool:
    text_clean = strip_punctuation(text.lower())
    return pattern.search(text_clean) is not None


def matches_loose(text: str, terms: list[str]) -> bool:
    text_lower = text.lower()
    return all(term in text_lower for term in terms)


def search_clues(search_term: str, output_dir: str = OUTPUT_DIR, mode: str = "strict") -> list[dict]:
    results = []

    if mode == "strict":
        search_clean = strip_punctuation(search_term.lower())
        pattern = re.compile(r'(?:^|\s)' + re.escape(search_clean) + r'(?:\s|$)')
        match_fn = lambda text: matches_strict(text, pattern)
    else:
        terms = [t.lower() for t in search_term.split()]
        match_fn = lambda text: matches_loose(text, terms)

    if not os.path.exists(output_dir):
        return results

    for root, dirs, files in os.walk(output_dir):
        folder_name = os.path.basename(root)
        season = folder_name.replace('season_', '') if folder_name.startswith('season_') else ''

        for filename in files:
            if not filename.endswith('.csv'):
                continue

            filepath = os.path.join(root, filename)
            game_date = filename.replace('.csv', '').split('_')[0]

            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    question = row.get('question', '')
                    answer = row.get('answer', '')

                    category = row.get('category', '')
                    combined = question + ' ' + answer + ' ' + category
                    if mode == 'loose':
                        matched = match_fn(combined)
                    else:
                        matched = match_fn(question) or match_fn(answer) or match_fn(category)
                    if matched:
                        results.append({
                            'date': game_date,
                            'season': season,
                            'category': category,
                            'value': row.get('value', ''),
                            'round': row.get('round', ''),
                            'question': question,
                            'answer': answer,
                            'days_ago': days_since(game_date),
                            'dollar_value': parse_value(row.get('value', ''))
                        })

    results.sort(key=lambda x: x['date'], reverse=True)
    return results


def calculate_scores(matches: list[dict]) -> tuple[float, float]:
    frequency_score = 0.0
    value_score = 0.0
    for m in matches:
        recency_weight = math.exp(-RECENCY_DECAY_RATE * m['days_ago'])
        frequency_score += recency_weight
        value_score += m['dollar_value'] * recency_weight
    return frequency_score, value_score