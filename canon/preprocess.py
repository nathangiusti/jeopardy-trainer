"""Load all game CSVs into a normalized clue table with entity keys.

Answers are normalized into entity keys (lowercase, accent-stripped, articles
and parentheticals removed) and then merged across alias variants: plurals,
parenthetical alternates, and unambiguous surname <-> full-name pairs
("dali" -> "salvador dali"). Question text is mined for capitalized-run
mentions so figures like Shakespeare, who appear in clues far more often
than as answers, still register.
"""

import csv
import json
import os
import re
import string
import unicodedata
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# A surname alias only merges into a full name when that full name is the
# single frequent answer ending in the surname (rules out "washington").
SURNAME_MIN_COUNT = 3
MENTION_ONLY_MIN_COUNT = 30

_PUNCT_TABLE = str.maketrans('', '', string.punctuation.replace('-', '') + '’‘“”')


def strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if not unicodedata.combining(c))


def normalize_key(text: str) -> str:
    """Reduce an answer or mention to a canonical entity key."""
    text = strip_accents(text.lower())
    text = text.translate(_PUNCT_TABLE)
    text = re.sub(r'^(a|an|the) ', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def split_answer(raw: str) -> tuple[str, list[str]]:
    """Split a raw answer into main text and parenthetical alternates."""
    alternates = []
    for m in re.finditer(r'\(([^)]*)\)', raw):
        inner = m.group(1).strip()
        # Alternates look like "(Dwyane) Wade" or "(or Burma)"; drop
        # commentary like "(accepted: ...)" only if it has no letters left
        inner = re.sub(r'^(or|aka|a\.k\.a\.|accept(ed)?:?)\s+', '', inner, flags=re.I)
        if inner:
            alternates.append(inner)
    main = re.sub(r'\([^)]*\)', ' ', raw)
    main = re.sub(r'\s+', ' ', main).strip()
    # "(Dwyane) Wade" style: alternate is a fuller form including the main
    full_forms = [f"{alt} {main}" for alt in alternates if main and alt and ' ' not in main]
    return main, alternates + full_forms


def is_skippable_answer(key: str) -> bool:
    if len(key) < 2:
        return True
    # Pure numbers ("3", "1,200", "6th") are not studyable entities
    if re.fullmatch(r'[\d\s,.-]+(st|nd|rd|th)?', key):
        return True
    return False


def load_merge_overrides() -> dict[str, str]:
    path = os.path.join(DATA_DIR, "merge_overrides.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_stoplist() -> set[str]:
    path = os.path.join(DATA_DIR, "stoplist.txt")
    stop = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#')[0].strip()
            if line:
                stop.add(line.lower())
    return stop


def load_clues(output_dir: str = OUTPUT_DIR) -> list[dict]:
    """Load every clue from every season CSV, oldest first."""
    clues = []
    season_dirs = sorted(
        (d for d in os.listdir(output_dir) if d.startswith('season_')),
        key=lambda d: int(d.split('_')[1]))
    for season_dir in season_dirs:
        season = int(season_dir.split('_')[1])
        full_dir = os.path.join(output_dir, season_dir)
        for filename in sorted(os.listdir(full_dir)):
            if not filename.endswith('.csv'):
                continue
            date = filename[:10]
            with open(os.path.join(full_dir, filename), encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    answer = (row.get('answer') or '').strip()
                    question = (row.get('question') or '').strip()
                    if not answer or not question:
                        continue
                    main, alternates = split_answer(answer)
                    key = normalize_key(main)
                    if is_skippable_answer(key):
                        continue
                    clues.append({
                        'date': date,
                        'season': season,
                        'category': (row.get('category') or '').strip().upper(),
                        'value': row.get('value') or '',
                        'round': row.get('round') or '',
                        'question': question,
                        'answer': answer,
                        'display': main or answer,
                        'key': key,
                        'alt_keys': [k for k in (normalize_key(a) for a in alternates)
                                     if k and not is_skippable_answer(k)],
                    })
    return clues


def build_merge_map(clues: list[dict]) -> dict[str, str]:
    """Map each raw entity key to its canonical (merged) key."""
    counts = Counter(c['key'] for c in clues)
    merge = {}

    # Parenthetical alternates: the fuller "(Dwyane) Wade" -> "dwyane wade"
    # form wins when it is itself a known key; otherwise leave as-is.
    alt_votes = defaultdict(Counter)
    for c in clues:
        for alt in c['alt_keys']:
            alt_votes[c['key']][alt] += 1
    for key, votes in alt_votes.items():
        best, n = votes.most_common(1)[0]
        # Merge into the fuller form when the alternate extends the key
        # (e.g. "wade" -> "dwyane wade") and is used consistently.
        if best.endswith(' ' + key) or best.startswith(key + ' '):
            if n >= max(2, counts[key] // 2):
                merge[key] = best

    # Plural -> singular only when the plural is rare next to the singular;
    # frequent plurals ("Queens" the borough vs "queen") are real entities.
    for key, n in counts.items():
        if key in merge:
            continue
        for singular in (key[:-2] if key.endswith('es') else None,
                         key[:-1] if key.endswith('s') else None):
            if singular and counts.get(singular, 0) >= max(4 * n, n + 3):
                merge[key] = singular
                break

    # Surname -> full name when unambiguous among frequent multi-word keys.
    # The full form must be at least as common as the bare word, or primary
    # entities get swallowed by an incidental compound ("australia" is not an
    # alias of "western australia"; "mercury" is not Freddie Mercury).
    surname_owners = defaultdict(list)
    for key, n in counts.items():
        if ' ' in key and n >= SURNAME_MIN_COUNT:
            surname_owners[key.split()[-1]].append((n, key))
    for surname, owners in surname_owners.items():
        if surname in counts and surname not in merge and len(owners) == 1:
            n_full, full = owners[0]
            if n_full >= counts[surname]:
                merge[surname] = full

    # Manual merges (canon/data/merge_overrides.json) are authoritative:
    # curated pairs the frequency guard can't prove safe automatically
    # ("ibsen" -> "henrik ibsen"; bare "Ibsen" answers outnumber the full
    # form, but they are the same person — unlike "mercury"/Freddie Mercury)
    # plus variant full forms ("js bach" -> "johann sebastian bach").
    merge.update(load_merge_overrides())

    # Resolve chains (plural -> singular -> full name)
    def resolve(k):
        seen = set()
        while k in merge and k not in seen:
            seen.add(k)
            k = merge[k]
        return k
    return {k: resolve(k) for k in merge}


# Capitalized runs of 1+ words, allowing internal lowercase connectors
# ("Joan of Arc", "Isabella I of Castile" won't fully match but their core will)
_MENTION_RE = re.compile(
    r"\b([A-Z][A-Za-z'’-]+(?:\s+(?:of|the|de|la|von|van|da|di)?\s*[A-Z][A-Za-z'’-]+)*)")
_LEADING_PAREN_RE = re.compile(r'^\([^)]*\)\s*')


def extract_mentions(question: str, stoplist: set[str]) -> list[str]:
    """Extract normalized candidate entity mentions from question text."""
    # Drop the leading "(Sarah of the Clue Crew ...)" stage directions
    text = _LEADING_PAREN_RE.sub('', question)
    mentions = []
    for m in _MENTION_RE.finditer(text):
        phrase = m.group(1).strip()
        # Sentence-initial single words are usually not entities
        start = m.start(1)
        at_start = start == 0 or text[max(0, start - 2):start].strip() in ('.', '!', '?', ';', ':', '"', '--')
        words = phrase.split()
        if at_start and len(words) == 1:
            continue
        key = normalize_key(phrase)
        if len(key) < 3 or key in stoplist:
            continue
        mentions.append(key)
    return mentions
