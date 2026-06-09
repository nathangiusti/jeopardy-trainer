import csv
from datetime import datetime
from search_core import OUTPUT_DIR, search_clues, calculate_scores

SEARCH_TERM = "louis armstrong"
SEARCH_MODE = "strict"   # "strict" or "loose"
OUTPUT_MODE = "stdout"   # "stdout" or "csv"


def output_to_stdout(results: list[dict], search_term: str):
    frequency_score, value_score = calculate_scores(results)
    print(f"'{search_term}' - Frequency: {frequency_score:.2f}, Value: {value_score:.2f}")
    print(f"{'='*60}\n")
    for r in results:
        print(f"[{r['date']}] {r['category']} ({r['value'] or 'Final'})")
        print(f"Q: {r['question']}")
        print(f"A: {r['answer']}")
        print("-" * 60)


def output_to_csv(results: list[dict], search_term: str):
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
    results = search_clues(SEARCH_TERM, OUTPUT_DIR, SEARCH_MODE)
    if not results:
        print(f"No matches found for '{SEARCH_TERM}'")
        return
    if OUTPUT_MODE == "csv":
        output_to_csv(results, SEARCH_TERM)
    else:
        output_to_stdout(results, SEARCH_TERM)


if __name__ == "__main__":
    main()