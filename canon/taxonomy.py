"""Map category titles to the curated Domain -> Topic taxonomy."""

import json
import os
import re
from collections import Counter, defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OVERRIDES_FILE = os.path.join(DATA_DIR, "category_overrides.json")
UNCLASSIFIED = "Unclassified"

# Topics that describe a category's format, not a knowledge domain. Their
# clues test real facts wearing a gimmick, so these topics never vote when
# deciding which domain an entity belongs to.
FORMAT_TOPICS = {
    "Before & After", "Rhymes, Puns & Puzzles", "Letter-Count Words",
    "Common Bonds & Stupid Answers", "Hodgepodge",
}


def load_taxonomy() -> dict[str, list[str]]:
    with open(os.path.join(DATA_DIR, "taxonomy.json"), encoding='utf-8') as f:
        return json.load(f)


class CategoryClassifier:
    def __init__(self):
        with open(os.path.join(DATA_DIR, "category_map.json"), encoding='utf-8') as f:
            data = json.load(f)
        self.exact = data['exact']
        self.keywords = [(re.compile(pat), topic) for pat, topic in data['keywords']]
        self.overrides = {}
        if os.path.exists(OVERRIDES_FILE):
            with open(OVERRIDES_FILE, encoding='utf-8') as f:
                self.overrides = json.load(f)
        taxonomy = load_taxonomy()
        self.topic_to_domain = {t: d for d, topics in taxonomy.items() for t in topics}
        # Fail fast if a rule points at a topic missing from taxonomy.json
        for topic in list(self.exact.values()) + [t for _, t in self.keywords]:
            if topic not in self.topic_to_domain:
                raise ValueError(f"rule topic not in taxonomy: {topic}")
        self._cache = {}

    def classify(self, category: str) -> str:
        """Return the topic for a category title (UNCLASSIFIED if no rule hits)."""
        if category in self._cache:
            return self._cache[category]
        topic = self.overrides.get(category) or self.exact.get(category)
        if topic is None:
            # Classify by content, not gimmick: '"C"OUNTRIES' and 'GEOGRAPHY "B"'
            # are geography categories wearing a spelling constraint.
            degimmicked = category.replace('"', '')
            for pattern, t in self.keywords:
                if pattern.search(degimmicked):
                    topic = t
                    break
        topic = topic or UNCLASSIFIED
        self._cache[category] = topic
        return topic


def assign_entity_topics(entity: dict, clue_topics: list,
                         max_topics: int = 2) -> list[str]:
    """An entity's topics = the most common topics of the clues it answered."""
    votes = Counter()
    for i in entity['answer_clues']:
        topic = clue_topics[i]
        if topic != UNCLASSIFIED and topic not in FORMAT_TOPICS:
            votes[topic] += 1
    top = votes.most_common()
    # A topic claim needs at least 2 classified clues AND a real share of the
    # entity's answers, or grab-bag entities adopt whichever topic ties first.
    min_votes = max(2, 0.15 * len(entity['answer_clues']))
    top = [(t, n) for t, n in top if n >= min_votes]
    if not top:
        return [UNCLASSIFIED]
    best_n = top[0][1]
    return [t for t, n in top[:max_topics] if n >= best_n * 0.3]
