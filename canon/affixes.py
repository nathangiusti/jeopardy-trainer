"""Mine prefix/suffix word families from answers.

Jeopardy leans hard on classical word parts, especially in science and
vocabulary categories: know that -ology = "study of" and arachno- = "spider"
and half the battle is decoding the word. This module scans every
single-word answer for a curated list of Greek/Latin affixes and groups
the recurring words into study families.

Curation notes: each affix carries a meaning string; per-affix blocklists
drop false cognates (George is not geo- "earth"); length guards drop words
barely longer than the affix itself (neon is not neo- "new").
"""

from collections import Counter

# (affix, kind, meaning) — kind is 'prefix' or 'suffix'
AFFIXES = [
    # -- prefixes: science & Greek/Latin roots --
    ('anthropo', 'prefix', 'human'),
    ('arachno', 'prefix', 'spider'),
    ('astro', 'prefix', 'star'),
    ('biblio', 'prefix', 'book'),
    ('bio', 'prefix', 'life'),
    ('cardio', 'prefix', 'heart'),
    ('chrono', 'prefix', 'time'),
    ('crypto', 'prefix', 'hidden, secret'),
    ('deca', 'prefix', 'ten'),
    ('demo', 'prefix', 'the people'),
    ('gastro', 'prefix', 'stomach'),
    ('geo', 'prefix', 'earth'),
    ('hemo', 'prefix', 'blood'),
    ('hydro', 'prefix', 'water'),
    ('hypno', 'prefix', 'sleep'),
    ('ichthyo', 'prefix', 'fish'),
    ('litho', 'prefix', 'stone'),
    ('macro', 'prefix', 'large'),
    ('mega', 'prefix', 'large, million'),
    ('micro', 'prefix', 'small'),
    ('mono', 'prefix', 'one, single'),
    ('necro', 'prefix', 'death'),
    ('neo', 'prefix', 'new'),
    ('octo', 'prefix', 'eight'),
    ('omni', 'prefix', 'all'),
    ('ornitho', 'prefix', 'bird'),
    ('paleo', 'prefix', 'ancient'),
    ('penta', 'prefix', 'five'),
    ('philo', 'prefix', 'loving'),
    ('phono', 'prefix', 'sound'),
    ('photo', 'prefix', 'light'),
    ('poly', 'prefix', 'many'),
    ('proto', 'prefix', 'first'),
    ('pseudo', 'prefix', 'false'),
    ('psycho', 'prefix', 'mind'),
    ('pyro', 'prefix', 'fire'),
    ('quadr', 'prefix', 'four'),
    ('tele', 'prefix', 'far, distant'),
    ('theo', 'prefix', 'god'),
    ('thermo', 'prefix', 'heat'),
    ('xeno', 'prefix', 'foreign, strange'),
    ('zoo', 'prefix', 'animal'),
    # -- suffixes --
    ('archy', 'suffix', 'rule, government'),
    ('cide', 'suffix', 'killing'),
    ('cracy', 'suffix', 'rule by'),
    ('crat', 'suffix', 'member of a ruling class'),
    ('ectomy', 'suffix', 'surgical removal'),
    ('ette', 'suffix', 'small, diminutive'),
    ('gamy', 'suffix', 'marriage'),
    ('gram', 'suffix', 'something written or recorded'),
    ('graphy', 'suffix', 'writing, recording'),
    ('hedron', 'suffix', 'solid with faces'),
    ('ism', 'suffix', 'doctrine, belief, practice'),
    ('itis', 'suffix', 'inflammation'),
    ('mania', 'suffix', 'madness, craze'),
    ('meter', 'suffix', 'measuring instrument'),
    ('nomy', 'suffix', 'system of laws or knowledge'),
    ('ology', 'suffix', 'study of'),
    ('ologist', 'suffix', 'one who studies'),
    ('onym', 'suffix', 'word, name'),
    ('osis', 'suffix', 'condition, process'),
    ('phile', 'suffix', 'lover of'),
    ('philia', 'suffix', 'love of'),
    ('phobia', 'suffix', 'fear of'),
    ('phone', 'suffix', 'sound instrument'),
    ('phyte', 'suffix', 'plant'),
    ('polis', 'suffix', 'city'),
    ('saurus', 'suffix', 'lizard'),
    ('scope', 'suffix', 'viewing instrument'),
    ('stan', 'suffix', 'land of (Persian)'),
    ('vore', 'suffix', 'eater'),
]

# False cognates: right letters, wrong root.
BLOCKLIST = {
    'geo': {'george', 'georges', 'georgia', 'georgian', 'georgians',
            'georgetown', 'geoffrey', 'geordie'},
    'demo': {'demolition', 'demolish', 'demolished'},
    'theo': {'theodore', 'theodora', 'theodosia'},
    'deca': {'decatur', 'decay'},
    'neo': {'neopolitan'},
    'mania': {'romania', 'tasmania'},
    'archy': {'starchy'},
    'saurus': {'thesaurus'},
    'cide': {'decide', 'coincide'},
    'osis': {'moses'},
}

MIN_WORD_COUNT = 2       # word must be an answer at least this often
MIN_FAMILY_SIZE = 3      # affix must collect at least this many words
MAX_WORDS_PER_AFFIX = 40


def _matches(word, affix, kind):
    if kind == 'prefix':
        return word.startswith(affix) and len(word) >= len(affix) + 3
    return word.endswith(affix) and len(word) >= len(affix) + 2


def mine_affixes(clues, merge, ents):
    """Return affix families: [{affix, kind, meaning, total, words}]."""
    counts = Counter()
    for c in clues:
        key = c['key']
        key = merge.get(key, key)
        if key and ' ' not in key and key.isalpha():
            counts[key] += 1
    words = [(w, n) for w, n in counts.items() if n >= MIN_WORD_COUNT]

    families = []
    for affix, kind, meaning in AFFIXES:
        blocked = BLOCKLIST.get(affix, ())
        hits = [(w, n) for w, n in words
                if w not in blocked and _matches(w, affix, kind)]
        if len(hits) < MIN_FAMILY_SIZE:
            continue
        hits.sort(key=lambda x: (-x[1], x[0]))
        families.append({
            'affix': affix + '-' if kind == 'prefix' else '-' + affix,
            'kind': kind,
            'meaning': meaning,
            'total': sum(n for _, n in hits),
            'words': [{'key': w,
                       'display': ents[w]['display'] if w in ents else w,
                       'count': n}
                      for w, n in hits[:MAX_WORDS_PER_AFFIX]],
        })
    families.sort(key=lambda f: (f['kind'] == 'prefix', -f['total']))
    return families
