"""Aggregate clues into canon entities with recency-weighted scores.

The score is sum(exp(-lambda * days_ago)) over answer occurrences plus a
reduced weight for question-text mentions, so a clue asked last season
counts for far more than one from 1999. The half-life sets how fast old
material fades.
"""

import math
from collections import Counter, defaultdict
from datetime import date

from . import preprocess, mentions as mentions_mod

HALF_LIFE_DAYS = 6 * 365
DECAY = math.log(2) / HALF_LIFE_DAYS
MENTION_WEIGHT = 0.3
MIN_ANSWER_COUNT = 3
MIN_MENTION_COUNT = 30

# Trend windows: recent 5 years vs the 10 years before that
TREND_RECENT_YEARS = 5
TREND_PRIOR_YEARS = 10


def parse_date(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def build_mention_alias_index(canonical_counts: Counter) -> dict[str, str]:
    """Map bare surnames to their unique frequent full-name entity."""
    owners = defaultdict(list)
    for key, n in canonical_counts.items():
        words = key.split()
        if len(words) > 1 and n >= MIN_ANSWER_COUNT:
            owners[words[-1]].append(key)
    return {surname: keys[0] for surname, keys in owners.items()
            if len(keys) == 1 and surname not in canonical_counts}


def build_entities(clues: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
    """Return (entities keyed by canonical key, merge map used)."""
    merge = preprocess.build_merge_map(clues)
    stoplist = preprocess.load_stoplist()

    ref_date = max(parse_date(c['date']) for c in clues)
    ref_year = ref_date.year

    canonical_counts = Counter(merge.get(c['key'], c['key']) for c in clues)
    surname_alias = build_mention_alias_index(canonical_counts)
    all_mentions = mentions_mod.extract_all(clues, stoplist)

    entities = defaultdict(lambda: {
        'answer_clues': [], 'mention_clues': [],
        'score': 0.0, 'displays': Counter(),
        'years': Counter(), 'years_mention': Counter(),
    })

    mention_only_counts = Counter()
    mention_hits = []  # (clue_idx, canonical_key, weight)

    for i, c in enumerate(clues):
        days_ago = (ref_date - parse_date(c['date'])).days
        weight = math.exp(-DECAY * days_ago)
        key = merge.get(c['key'], c['key'])
        e = entities[key]
        e['answer_clues'].append(i)
        e['score'] += weight
        e['displays'][c['display']] += 1
        e['years'][c['date'][:4]] += 1

        seen_in_clue = set()
        for m in all_mentions[i]:
            mk = merge.get(m, m)
            mk = surname_alias.get(mk, mk)
            if mk == key or mk in seen_in_clue:
                continue
            seen_in_clue.add(mk)
            mention_hits.append((i, mk, weight))
            if mk not in canonical_counts:
                mention_only_counts[mk] += 1

    keep_mention_only = {k for k, n in mention_only_counts.items()
                         if n >= MIN_MENTION_COUNT}

    for i, mk, weight in mention_hits:
        if mk in canonical_counts or mk in keep_mention_only:
            e = entities[mk]
            e['mention_clues'].append(i)
            e['score'] += MENTION_WEIGHT * weight
            e['years_mention'][clues[i]['date'][:4]] += 1

    # Reverse aliases for search: raw keys that merge into each canonical key
    aliases = defaultdict(set)
    for raw, canon in merge.items():
        aliases[canon].add(raw)
    for surname, canon in surname_alias.items():
        aliases[canon].add(surname)

    result = {}
    for key, e in entities.items():
        n_ans = len(e['answer_clues'])
        n_men = len(e['mention_clues'])
        if n_ans < MIN_ANSWER_COUNT and n_men < MIN_MENTION_COUNT:
            continue
        if e['displays']:
            # Prefer the answer text that spells out the canonical key, so a
            # merged entity shows "Henrik Ibsen" even though bare "Ibsen" is
            # the more common way the show writes the answer.
            full_forms = [(n, d) for d, n in e['displays'].items()
                          if preprocess.normalize_key(d) == key]
            if full_forms:
                display = max(full_forms)[1]
            else:
                display = e['displays'].most_common(1)[0][0]
        else:
            display = key.title()
        result[key] = {
            'key': key,
            'display': display,
            'aliases': sorted(aliases.get(key, ())),
            'answer_count': n_ans,
            'mention_count': n_men,
            'score': round(e['score'], 2),
            'years': dict(e['years']),
            'years_mention': dict(e['years_mention']),
            'trend': classify_trend(e['years'], ref_year),
            'answer_clues': e['answer_clues'],
            'mention_clues': e['mention_clues'],
        }
    return result, merge


def classify_trend(years: Counter, ref_year: int) -> str:
    recent = sum(n for y, n in years.items()
                 if int(y) > ref_year - TREND_RECENT_YEARS)
    prior = sum(n for y, n in years.items()
                if ref_year - TREND_RECENT_YEARS >= int(y)
                > ref_year - TREND_RECENT_YEARS - TREND_PRIOR_YEARS)
    recent_rate = recent / TREND_RECENT_YEARS
    prior_rate = prior / TREND_PRIOR_YEARS
    if recent >= 5 and recent_rate > 1.5 * prior_rate:
        return 'rising'
    if prior >= 10 and recent_rate < 0.5 * prior_rate:
        return 'declining'
    return 'stable'
