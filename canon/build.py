"""Build canon_data.js for the knowledge-map UI.

Run:  python -m canon.build

Emits a single JS file (loaded via <script src> so canon_map.html works
straight off file://) containing the flat clue table, entity records,
per-topic stats, and cue-phrase associations.
"""

import csv
import json
import math
import os
import time
import zipfile
from collections import Counter, defaultdict

from . import preprocess, entities as entities_mod, taxonomy, associations as assoc_mod, affixes as affixes_mod, clue_classifier

# Artifacts live in canon/ (canon_map.html must sit next to
# canon_data.js for its relative <script src> to resolve).
OUT_FILE = os.path.join(preprocess.PKG_DIR, "canon_data.js")
HTML_FILE = os.path.join(preprocess.PKG_DIR, "canon_map.html")
ZIP_FILE = os.path.join(preprocess.PKG_DIR, "canon_map.zip")
REVIEW_FILE = os.path.join(preprocess.PKG_DIR, "canon_review.csv")
REVIEW_ROWS = 400


def harvest_review(clf) -> int:
    """Fold user-tagged rows from canon_review.csv into category_overrides.json."""
    if not os.path.exists(REVIEW_FILE):
        return 0
    added = 0
    with open(REVIEW_FILE, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            cat = (row.get('category') or '').strip()
            topic = (row.get('topic') or '').strip()
            if not cat or not topic:
                continue
            if topic not in clf.topic_to_domain and topic != taxonomy.UNCLASSIFIED:
                print(f"  WARNING: unknown topic {topic!r} for {cat!r} - skipped")
                continue
            if clf.overrides.get(cat) != topic:
                clf.overrides[cat] = topic
                added += 1
    if added:
        with open(taxonomy.OVERRIDES_FILE, 'w', encoding='utf-8') as f:
            json.dump(dict(sorted(clf.overrides.items())), f,
                      indent=1, ensure_ascii=False)
        clf._cache.clear()
    return added


def write_review(clues, clue_topics):
    """Emit the top unclassified categories as a worklist for manual tagging."""
    uncl = Counter()
    example = {}
    for c, t in zip(clues, clue_topics):
        if t == taxonomy.UNCLASSIFIED:
            uncl[c['category']] += 1
            example.setdefault(c['category'], (c['question'], c['answer']))
    with open(REVIEW_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['category', 'clue_count', 'topic', 'example_question', 'example_answer'])
        for cat, n in uncl.most_common(REVIEW_ROWS):
            q, a = example[cat]
            w.writerow([cat, n, '', q, a])


def _split_combo(words, merge, ents):
    """Find the component entities of a combo answer.

    Tries, in order: a 2-way split sharing one word (classic Before & After),
    a 3-way chain sharing two words (BEFORE, DURING & AFTER), and finally a
    disjoint 2-way split for combos whose bridge isn't itself a canon entity
    (Glenn Miller [Light] Brigade -> glenn miller + light brigade).
    """
    def k(ws):
        s = ' '.join(ws)
        return merge.get(s, s)
    n = len(words)
    for j in range(1, n - 1):
        lk, rk = k(words[:j + 1]), k(words[j:])
        if lk != rk and lk in ents and rk in ents:
            return [lk, rk]
    for i in range(1, n - 1):
        for j in range(i + 1, n - 1):
            ks = [k(words[:i + 1]), k(words[i:j + 1]), k(words[j:])]
            if len(set(ks)) == 3 and all(x in ents for x in ks):
                return ks
    for j in range(1, n):
        lk, rk = k(words[:j]), k(words[j:])
        if lk != rk and lk in ents and rk in ents:
            return [lk, rk]
    return None


def decompose_before_after(clues, clue_topics, merge, ents, ref_date):
    """Split B&A combo answers into component entities and credit each."""
    ref = entities_mod.parse_date(ref_date)
    counts = Counter()
    examples = defaultdict(list)
    for i, (c, topic) in enumerate(zip(clues, clue_topics)):
        if topic != 'Before & After':
            continue
        parts = _split_combo(c['key'].split(), merge, ents)
        if not parts:
            continue
        w = math.exp(-entities_mod.DECAY *
                     (ref - entities_mod.parse_date(c['date'])).days)
        yr = c['date'][:4]
        for k in parts:
            counts[k] += 1
            if len(examples[k]) < 3:
                examples[k].append(i)
            e = ents[k]
            e['mention_clues'].append(i)
            e['mention_count'] += 1
            e['score'] = round(e['score'] + entities_mod.MENTION_WEIGHT * w, 2)
            e['years_mention'][yr] = e['years_mention'].get(yr, 0) + 1
    return counts, examples


def build(output_dir: str = preprocess.OUTPUT_DIR, out_file: str = OUT_FILE):
    t0 = time.time()
    print("Loading clues...")
    clues = preprocess.load_clues(output_dir)
    print(f"  {len(clues)} clues")

    print("Building entities...")
    ents, merge = entities_mod.build_entities(clues)
    print(f"  {len(ents)} canon entities (answer count >= "
          f"{entities_mod.MIN_ANSWER_COUNT} or mentions >= {entities_mod.MIN_MENTION_COUNT})")

    print("Classifying categories...")
    clf = taxonomy.CategoryClassifier()
    tax = taxonomy.load_taxonomy()
    harvested = harvest_review(clf)
    if harvested:
        print(f"  harvested {harvested} manual tags from {os.path.basename(REVIEW_FILE)} into overrides")

    title_topics = [clf.classify(c['category']) for c in clues]
    title_classified = sum(1 for t in title_topics if t != taxonomy.UNCLASSIFIED)
    print(f"  title coverage: {title_classified / len(clues):.1%}")

    print("Training per-clue topic classifier...")
    clue_topics, filled = clue_classifier.fill_unclassified(clues, title_topics)
    classified = sum(1 for t in clue_topics if t != taxonomy.UNCLASSIFIED)
    print(f"  ML-filled {filled} clues (confidence >= "
          f"{clue_classifier.MIN_CONFIDENCE}); coverage now {classified / len(clues):.1%}")

    topic_stats = defaultdict(lambda: {'count': 0, 'years': Counter()})
    for c, topic in zip(clues, clue_topics):
        ts = topic_stats[topic]
        ts['count'] += 1
        ts['years'][c['date'][:4]] += 1

    print("Assigning entity topics...")
    for e in ents.values():
        e['topics'] = taxonomy.assign_entity_topics(e, clue_topics)

    print("Mining associations...")
    assocs = assoc_mod.mine_associations(clues, merge, ents)
    print(f"  {len(assocs)} associations")

    ref_date = max(c['date'] for c in clues)
    print("Decomposing Before & After answers...")
    ba_counts, ba_examples = decompose_before_after(clues, clue_topics, merge, ents, ref_date)
    print(f"  {sum(ba_counts.values())} half-credits across {len(ba_counts)} entities")

    print("Mining word-part families...")
    affix_families = affixes_mod.mine_affixes(clues, merge, ents)
    print(f"  {len(affix_families)} affix families")

    # Review worklist stays title-based: a manual tag for a whole category is
    # higher-quality than per-clue ML fills and should remain available.
    write_review(clues, title_topics)
    print(f"  wrote {os.path.basename(REVIEW_FILE)} (top unclassified categories; fill the topic column and rebuild)")

    print("Serializing...")
    ent_list = sorted(ents.values(), key=lambda e: -e['score'])
    ent_index = {e['key']: i for i, e in enumerate(ent_list)}

    topic_names = sorted(topic_stats)
    topic_idx = {t: i for i, t in enumerate(topic_names)}
    data = {
        'built': time.strftime('%Y-%m-%d'),
        'ref_date': ref_date,
        'half_life_days': entities_mod.HALF_LIFE_DAYS,
        'mention_weight': entities_mod.MENTION_WEIGHT,
        'clues': [[c['date'], c['category'], c['value'], c['round'],
                   c['question'], c['answer']] for c in clues],
        'topic_names': topic_names,
        'clue_topics': [topic_idx[t] for t in clue_topics],
        'taxonomy': tax,
        'topics': {
            t: {'count': s['count'], 'years': dict(s['years'])}
            for t, s in topic_stats.items()
        },
        'entities': [{
            'k': e['key'], 'd': e['display'], 'al': e['aliases'],
            'ac': e['answer_count'], 'mc': e['mention_count'],
            's': e['score'], 'y': e['years'], 'ym': e['years_mention'],
            't': e['trend'],
            'tp': e['topics'], 'a': e['answer_clues'], 'm': e['mention_clues'],
        } for e in ent_list],
        'before_after': [
            {'e': ent_index[k], 'n': n, 'x': ba_examples[k]}
            for k, n in ba_counts.most_common() if k in ent_index
        ],
        'affixes': [{
            'x': f['affix'], 'kind': f['kind'], 'm': f['meaning'], 'n': f['total'],
            'w': [{'d': w['display'], 'n': w['count'],
                   'e': ent_index.get(w['key'])} for w in f['words']],
        } for f in affix_families],
        'associations': [{
            'cue': a['cue'], 'kind': a['kind'], 'n': a['count'],
            's': a['score'],
            'ans': [{'e': ent_index.get(x['key']) if x['key'] else None,
                     'd': x['display'], 'n': x['count']} for x in a['answers']],
            'c': a['clues'],
        } for a in assocs],
    }

    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("const CANON_DATA = ")
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        f.write(";\n")

    size_mb = os.path.getsize(out_file) / 1e6
    print(f"\nWrote {os.path.basename(out_file)} ({size_mb:.1f} MB) in {time.time() - t0:.0f}s")

    # Shareable bundle: the page plus its data file is everything someone
    # needs to unzip and open canon_map.html locally. Flat arcnames so the
    # zip never embeds local directory paths.
    if os.path.exists(HTML_FILE):
        with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(HTML_FILE, arcname=os.path.basename(HTML_FILE))
            z.write(out_file, arcname=os.path.basename(out_file))
        print(f"Wrote {os.path.basename(ZIP_FILE)} ({os.path.getsize(ZIP_FILE) / 1e6:.1f} MB) "
              f"- unzip & open {os.path.basename(HTML_FILE)} to view")
    else:
        print(f"WARNING: {os.path.basename(HTML_FILE)} not found - skipped {os.path.basename(ZIP_FILE)}")

    print(f"Summary: {len(clues)} clues | {len(ent_list)} entities | "
          f"{len(assocs)} associations | ref date {ref_date}")


if __name__ == "__main__":
    build()
