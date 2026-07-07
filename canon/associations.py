"""Mine cue-phrase -> answer-set associations.

Jeopardy's signature construction is "this Dutch painter ...", so the
descriptor after "this/these" is the cue contestants actually key on.
When a cue's answers concentrate on a handful of entities ("Dutch painter"
-> Vermeer/Rembrandt/Mondrian), that pairing is studyable gold. A second
cue source is proper-noun mentions: if clues mentioning "Pyrenees" almost
always resolve to Andorra, that too becomes an association.
"""

import math
import re
from collections import Counter, defaultdict

from . import entities as entities_mod

MIN_CUE_COUNT = 8
TOP_ANSWERS = 4
MIN_CONCENTRATION = 0.5
MIN_MENTION_CUE_COUNT = 10
# Two cues drawing on mostly the same clues ("this verdi opera" inside
# "mentions Verdi") are one association; keep the stronger.
MAX_OVERLAP = 0.6

# Words that end a descriptor phrase ("this dutch painter OF the night watch")
_CUT_WORDS = {
    'who', 'whose', 'whom', 'that', 'which', 'was', 'is', 'are', 'were',
    'has', 'had', 'have', 'of', 'from', 'with', 'in', 'on', 'for', 'to',
    'at', 'by', 'and', 'or', 'can', 'could', 'named', 'called', 'seen',
    'whos', 'once', 'first', 'also', 'may', 'might', 'made', 'used',
    'born', 'known', 'said', 'the', 'a', 'an', 'its', 'his', 'her',
}
# Cues that are pure clue scaffolding with no study value
_GENERIC_CUES = {
    'man', 'woman', 'word', 'term', 'name', 'title', 'type', 'kind',
    'phrase', 'city', 'state', 'country', 'president', 'author', 'novel',
    'film', 'movie', 'show', 'song', 'book', 'play', 'river', 'island',
    'animal', 'body', 'one', 'company', 'group', 'letter', 'number',
    'color', 'sport', 'game', 'holiday', 'month', 'day', 'year', 'element',
    'actor', 'actress', 'singer', 'band', 'poet', 'artist', 'painter',
    'composer', 'king', 'queen', 'language', 'capital', 'sea', 'lake',
    'mountain', 'planet', 'bird', 'fish', 'dog', 'tree', 'flower', 'fruit',
}

_THIS_RE = re.compile(r"\bthis ([a-z][a-z'-]*(?: [a-z][a-z'-]*){0,2})")


def extract_cues(question: str) -> list[str]:
    """Descriptor phrases after 'this', trimmed at function words."""
    cues = []
    for m in _THIS_RE.finditer(question.lower()):
        words = []
        for w in m.group(1).split():
            if w in _CUT_WORDS:
                break
            words.append(w)
        if not words:
            continue
        cue = ' '.join(words)
        # Single generic nouns ("this man") carry no association signal
        if len(words) == 1 and (cue in _GENERIC_CUES or len(cue) < 4):
            continue
        cues.append(cue)
    return cues


def _summarize(cue_display, kind, hits, entities):
    """Turn (clue_idx, answer_key, weight) hits into an association record."""
    by_answer = Counter(k for _, k, _ in hits)
    total = sum(by_answer.values())
    top = by_answer.most_common(TOP_ANSWERS)
    coverage = sum(n for _, n in top) / total
    if coverage < MIN_CONCENTRATION or len(by_answer) > total * 0.8:
        return None
    weighted = sum(w for _, _, w in hits)
    return {
        'cue': cue_display,
        'kind': kind,
        'count': total,
        'score': round(weighted * coverage, 2),
        'answers': [
            {'key': k if k in entities else None,
             'display': entities[k]['display'] if k in entities else k.title(),
             'count': n}
            for k, n in top
        ],
        'clues': sorted({i for i, _, _ in hits}, reverse=True)[:40],
    }


def mine_associations(clues: list[dict], merge: dict[str, str],
                      entities: dict) -> list[dict]:
    ref_date = max(entities_mod.parse_date(c['date']) for c in clues)

    cue_hits = defaultdict(list)
    for i, c in enumerate(clues):
        key = merge.get(c['key'], c['key'])
        days_ago = (ref_date - entities_mod.parse_date(c['date'])).days
        weight = math.exp(-entities_mod.DECAY * days_ago)
        for cue in set(extract_cues(c['question'])):
            cue_hits[cue].append((i, key, weight))

    candidates = []  # (assoc record, full clue-index set)
    for cue, hits in cue_hits.items():
        if len(hits) < MIN_CUE_COUNT:
            continue
        assoc = _summarize(f'this {cue}', 'descriptor', hits, entities)
        if assoc:
            candidates.append((assoc, {i for i, _, _ in hits}))

    # Mention-based cues: clues mentioning entity X resolve to few answers
    for ent in entities.values():
        idxs = ent['mention_clues']
        if len(idxs) < MIN_MENTION_CUE_COUNT:
            continue
        hits = []
        for i in idxs:
            c = clues[i]
            key = merge.get(c['key'], c['key'])
            days_ago = (ref_date - entities_mod.parse_date(c['date'])).days
            hits.append((i, key, math.exp(-entities_mod.DECAY * days_ago)))
        assoc = _summarize(f'mentions {ent["display"]}', 'mention', hits, entities)
        if assoc:
            candidates.append((assoc, set(idxs)))

    return _dedupe(candidates)


def _dedupe(candidates):
    """Greedily keep the strongest association among clue-set near-duplicates."""
    candidates.sort(key=lambda x: -x[0]['score'])
    kept, kept_sets = [], []
    clue_owners = defaultdict(list)
    for assoc, cset in candidates:
        overlap = Counter()
        for i in cset:
            for k in clue_owners.get(i, ()):
                overlap[k] += 1
        if any(n / min(len(cset), len(kept_sets[k])) > MAX_OVERLAP
               for k, n in overlap.items()):
            continue
        kid = len(kept)
        kept.append(assoc)
        kept_sets.append(cset)
        for i in cset:
            clue_owners[i].append(kid)
    return kept
