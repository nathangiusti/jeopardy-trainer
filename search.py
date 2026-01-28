import csv
import os
import math
from datetime import datetime, date

# Configuration
SEARCH_TERM = "Camus"
OUTPUT_MODE = "stdout"  # "stdout" or "csv"
OUTPUT_DIR = "output"

# Scoring parameters
RECENCY_DECAY_RATE = 0.001  # For exponential decay: higher = faster decay
FINAL_JEOPARDY_VALUE = 4000  # Value assigned to Final Jeopardy


def parse_value(value_str: str) -> int:
    """Convert value string like '$800' to integer."""
    if not value_str:
        return FINAL_JEOPARDY_VALUE
    return int(value_str.replace('$', '').replace(',', ''))


def days_since(date_str: str) -> int:
    """Calculate days between a date string and today."""
    try:
        game_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        return (date.today() - game_date).days
    except:
        return 365 * 5  # Default to 5 years ago if parse fails


def search_clues(search_term: str, output_dir: str) -> list[dict]:
    """Search all CSV files for clues containing the search term."""
    results = []
    search_lower = search_term.lower()

    if not os.path.exists(output_dir):
        print(f"Output directory '{output_dir}' does not exist.")
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
                    question = row.get('question', '').lower()
                    answer = row.get('answer', '').lower()

                    if search_lower in question or search_lower in answer:
                        results.append({
                            'date': game_date,
                            'season': season,
                            'category': row.get('category', ''),
                            'value': row.get('value', ''),
                            'round': row.get('round', ''),
                            'question': row.get('question', ''),
                            'answer': row.get('answer', ''),
                            'days_ago': days_since(game_date),
                            'dollar_value': parse_value(row.get('value', ''))
                        })

    results.sort(key=lambda x: x['date'], reverse=True)
    return results


def calculate_scores(matches: list[dict]) -> tuple[float, float]:
    """Calculate frequency and value scores."""
    frequency_score = 0
    value_score = 0

    for m in matches:
        recency_weight = math.exp(-RECENCY_DECAY_RATE * m['days_ago'])
        frequency_score += recency_weight
        value_score += m['dollar_value'] * recency_weight

    return frequency_score, value_score


def output_to_stdout(results: list[dict], search_term: str):
    """Print scores and results to stdout."""
    frequency_score, value_score = calculate_scores(results)

    print(f"'{search_term}' - Frequency: {frequency_score:.2f}, Value: {value_score:.2f}")
    print(f"{'='*60}\n")

    for r in results:
        print(f"[{r['date']}] {r['category']} ({r['value'] or 'Final'})")
        print(f"Q: {r['question']}")
        print(f"A: {r['answer']}")
        print("-" * 60)


def output_to_csv(results: list[dict], search_term: str):
    """Write results to a CSV file."""
    frequency_score, value_score = calculate_scores(results)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_term = "".join(c if c.isalnum() else "_" for c in search_term)
    output_file = f"search_results_{safe_term}_{timestamp}.csv"

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['date', 'season', 'category', 'value', 'round', 'question', 'answer']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in fieldnames})

    print(f"'{search_term}' - Frequency: {frequency_score:.2f}, Value: {value_score:.2f}")
    print(f"Results saved to: {output_file}")


def main():
    results = search_clues(SEARCH_TERM, OUTPUT_DIR)

    if not results:
        print(f"No matches found for '{SEARCH_TERM}'")
        return

    if OUTPUT_MODE == "csv":
        output_to_csv(results, SEARCH_TERM)
    else:
        output_to_stdout(results, SEARCH_TERM)


if __name__ == "__main__":
    main()
