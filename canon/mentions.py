"""Question-text mention extraction via spaCy NER, with a disk cache.

Replaces the capitalized-run regex: real named-entity recognition catches
multiword names the regex splits ("Joan of Arc"), skips sentence-initial
false positives, and never tags dates or numbers. Results are cached in
mention_cache.pkl (gitignored) keyed by question-text hash, so the model
cost is paid once per new clue; a full cold run over all ~364k questions
takes a few minutes, later builds are near-instant.

Falls back to the old regex extractor (with a warning) if spaCy or its
en_core_web_sm model is unavailable.
"""

import hashlib
import os
import pickle

from . import preprocess

CACHE_FILE = "mention_cache.pkl"
BATCH_SIZE = 512
SAVE_EVERY = 100000

# Entity labels that can be canon material; DATE/TIME/CARDINAL etc. are not.
NER_LABELS = {
    'PERSON', 'GPE', 'LOC', 'ORG', 'FAC', 'NORP', 'WORK_OF_ART',
    'EVENT', 'PRODUCT', 'LANGUAGE', 'LAW',
}


def _save(cache):
    with open(CACHE_FILE, 'wb') as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)


def extract_all(clues, stoplist):
    """Return a list of normalized mention keys for every clue, in order."""
    texts = [preprocess._LEADING_PAREN_RE.sub('', c['question']) for c in clues]
    hashes = [hashlib.md5(t.encode('utf-8')).hexdigest() for t in texts]

    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'rb') as f:
            cache = pickle.load(f)

    missing = [i for i, h in enumerate(hashes) if h not in cache]
    if missing:
        try:
            import spacy
            nlp = spacy.load('en_core_web_sm',
                             disable=['tagger', 'parser', 'attribute_ruler', 'lemmatizer'])
        except Exception as exc:
            print(f"  WARNING: spaCy unavailable ({exc}); using regex mentions")
            return [preprocess.extract_mentions(c['question'], stoplist)
                    for c in clues]
        print(f"  NER on {len(missing)} new questions "
              f"({len(clues) - len(missing)} cached)...")
        done = 0
        docs = nlp.pipe((texts[i] for i in missing), batch_size=BATCH_SIZE)
        for i, doc in zip(missing, docs):
            cache[hashes[i]] = [(ent.text, ent.label_) for ent in doc.ents]
            done += 1
            if done % SAVE_EVERY == 0:
                _save(cache)
                print(f"    {done}/{len(missing)}")
        _save(cache)

    out = []
    for h in hashes:
        ments = []
        for text, label in cache[h]:
            if label not in NER_LABELS:
                continue
            if text.endswith(("'s", "’s")):
                text = text[:-2]
            key = preprocess.normalize_key(text)
            if len(key) >= 3 and key not in stoplist:
                ments.append(key)
        out.append(ments)
    return out
