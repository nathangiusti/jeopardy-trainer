import requests
from bs4 import BeautifulSoup
import csv
import os
import re
import time

# Configuration - Seasons to parse
SEASONS_TO_PARSE = [42]

# Base URLs
SEASON_URL = "https://j-archive.com/showseason.php?season={}"
GAME_URL = "https://j-archive.com/showgame.php?game_id={}"

# Output directory
OUTPUT_DIR = "output"


def get_game_ids_for_season(season: int) -> list[int]:
    """Fetch all game IDs for a given season."""
    url = SEASON_URL.format(season)
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    game_ids = []

    for link in soup.find_all('a', href=True):
        href = link['href']
        match = re.search(r'game_id=(\d+)', href)
        if match:
            game_ids.append(int(match.group(1)))

    return list(set(game_ids))


def parse_clue_text(element) -> str:
    """Extract text from a clue, handling any nested elements."""
    if element is None:
        return ""
    text = element.get_text(separator=" ", strip=True)
    return re.sub(r'\s+', ' ', text).strip()


def get_game_date(soup: BeautifulSoup) -> str:
    """Extract the air date from the game page."""
    title = soup.find('title')
    if title:
        title_text = title.get_text()
        # Title format is typically "J! Archive - Show #XXXX, aired YYYY-MM-DD"
        match = re.search(r'aired\s+(\d{4}-\d{2}-\d{2})', title_text)
        if match:
            return match.group(1)
    return "unknown_date"


def parse_game(game_id: int) -> tuple[str, list[dict]]:
    """Parse a single game and return the date and list of clues."""
    url = GAME_URL.format(game_id)
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    game_date = get_game_date(soup)
    clues = []

    # Parse Jeopardy round
    jeopardy_round = soup.find('div', id='jeopardy_round')
    if jeopardy_round:
        clues.extend(parse_round(jeopardy_round, "jeopardy"))

    # Parse Double Jeopardy round
    double_jeopardy_round = soup.find('div', id='double_jeopardy_round')
    if double_jeopardy_round:
        clues.extend(parse_round(double_jeopardy_round, "double jeopardy"))

    # Parse Final Jeopardy
    final_round = soup.find('div', id='final_jeopardy_round')
    if final_round:
        clues.extend(parse_final_jeopardy(final_round))

    return game_date, clues


def parse_round(round_div, round_name: str) -> list[dict]:
    """Parse a Jeopardy or Double Jeopardy round."""
    clues = []

    # Get categories
    categories = []
    category_elements = round_div.find_all('td', class_='category_name')
    for cat in category_elements:
        categories.append(parse_clue_text(cat))

    # Get clues
    clue_elements = round_div.find_all('td', class_='clue')

    for clue_td in clue_elements:
        # Get the clue text - find the visible one (not the _r hidden one)
        all_clue_texts = clue_td.find_all('td', class_='clue_text')
        clue_text_div = None
        answer_div = None

        for td in all_clue_texts:
            td_id = td.get('id', '')
            if td_id.endswith('_r'):
                answer_div = td
            elif td_id and not td_id.endswith('_r'):
                clue_text_div = td

        if not clue_text_div:
            continue

        question = parse_clue_text(clue_text_div)
        if not question:
            continue

        # Get the clue ID to determine category and value
        clue_id = clue_text_div.get('id', '')
        # ID format: clue_J_1_1 (round_column_row) or clue_DJ_1_1
        match = re.match(r'clue_(D?J)_(\d+)_(\d+)', clue_id)
        if not match:
            continue

        col = int(match.group(2)) - 1  # 0-indexed
        row = int(match.group(3))

        # Get category
        category = categories[col] if col < len(categories) else "Unknown"

        # Calculate value based on row (row 1 = $200/$400, row 2 = $400/$800, etc.)
        base_value = 200 if round_name == "jeopardy" else 400
        value = base_value * row

        # Get answer from the hidden _r div
        answer = ""
        if answer_div:
            correct_response = answer_div.find('em', class_='correct_response')
            if correct_response:
                answer = parse_clue_text(correct_response)

        clues.append({
            'category': category,
            'value': f"${value}",
            'round': round_name,
            'question': question,
            'answer': answer
        })

    return clues


def parse_final_jeopardy(final_div) -> list[dict]:
    """Parse the Final Jeopardy round."""
    clues = []

    # Get category
    category_elem = final_div.find('td', class_='category_name')
    category = parse_clue_text(category_elem) if category_elem else "Final Jeopardy"

    # Get clue
    clue_elem = final_div.find('td', class_='clue_text')
    question = parse_clue_text(clue_elem) if clue_elem else ""

    # Get answer
    answer = ""
    # Final Jeopardy answer is typically in a separate element
    answer_elem = final_div.find('em', class_='correct_response')
    if answer_elem:
        answer = parse_clue_text(answer_elem)

    if question:
        clues.append({
            'category': category,
            'value': '',  # Final Jeopardy has no set value
            'round': 'final',
            'question': question,
            'answer': answer
        })

    return clues


def save_game_to_csv(game_date: str, clues: list[dict], output_dir: str, season: int):
    """Save game clues to a CSV file in a season-specific folder."""
    season_dir = os.path.join(output_dir, f"season_{season}")
    os.makedirs(season_dir, exist_ok=True)

    filename = os.path.join(season_dir, f"{game_date}.csv")

    # Handle duplicate dates by appending a number
    base_filename = filename
    counter = 1
    while os.path.exists(filename):
        filename = base_filename.replace('.csv', f'_{counter}.csv')
        counter += 1

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['category', 'value', 'round', 'question', 'answer']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for clue in clues:
            writer.writerow(clue)

    print(f"Saved: {filename}")


def get_existing_dates_for_season(output_dir: str, season: int) -> set[str]:
    """Get set of dates that already have CSVs generated for a specific season."""
    existing = set()
    season_dir = os.path.join(output_dir, f"season_{season}")
    if os.path.exists(season_dir):
        for filename in os.listdir(season_dir):
            if filename.endswith('.csv'):
                # Extract date from filename (handles both YYYY-MM-DD.csv and YYYY-MM-DD_1.csv)
                date_match = re.match(r'(\d{4}-\d{2}-\d{2})', filename)
                if date_match:
                    existing.add(date_match.group(1))
    return existing


def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for season in SEASONS_TO_PARSE:
        print(f"\nProcessing Season {season}...")

        # Get already processed dates for this season
        existing_dates = get_existing_dates_for_season(OUTPUT_DIR, season)
        print(f"Found {len(existing_dates)} existing games for season {season}")

        game_ids = get_game_ids_for_season(season)
        print(f"Found {len(game_ids)} games in season {season}")

        for i, game_id in enumerate(game_ids):
            print(f"  Processing game {i+1}/{len(game_ids)} (ID: {game_id})...")

            try:
                # First fetch just the date to check if we already have it
                url = GAME_URL.format(game_id)
                response = requests.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                game_date = get_game_date(soup)

                if game_date in existing_dates:
                    print(f"    Skipping - already have {game_date}")
                    continue

                # Parse the full game (reuse the soup we already have)
                clues = []
                jeopardy_round = soup.find('div', id='jeopardy_round')
                if jeopardy_round:
                    clues.extend(parse_round(jeopardy_round, "jeopardy"))
                double_jeopardy_round = soup.find('div', id='double_jeopardy_round')
                if double_jeopardy_round:
                    clues.extend(parse_round(double_jeopardy_round, "double jeopardy"))
                final_round = soup.find('div', id='final_jeopardy_round')
                if final_round:
                    clues.extend(parse_final_jeopardy(final_round))

                save_game_to_csv(game_date, clues, OUTPUT_DIR, season)
                existing_dates.add(game_date)

                # Be polite to the server
                time.sleep(1)

            except Exception as e:
                print(f"    Error processing game {game_id}: {e}")
                continue

    print("\nDone!")


if __name__ == "__main__":
    main()
