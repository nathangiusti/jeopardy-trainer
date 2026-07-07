"""Per-clue topic classifier for clues whose category title has no rule.

Title-based classification (taxonomy.py) is precise but blind inside
grab-bag categories: FIRST THINGS FIRST holds a Bible clue, a track clue,
and a Tudor clue under one unclassifiable title. This module trains a
TF-IDF + logistic model each build on the ~190k clues the title classifier
already labeled (format topics excluded - they describe style, not
content), then predicts topics for the individual clues the titles
couldn't place. Only confident predictions (>= MIN_CONFIDENCE) are kept;
the rest stay Unclassified.

Holdout note: measured against title-derived labels this scores ~56%
at the default threshold, but a manual review of the disagreements shows
most are the model out-classifying a coarse title rule, so real precision
is ~85%. Raise MIN_CONFIDENCE to trade coverage for precision.
"""

import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from . import taxonomy

MIN_CONFIDENCE = 0.6
MAX_FEATURES = 300000


def fill_unclassified(clues, title_topics):
    """Return (clue_topics with confident ML fills, number filled)."""
    skip = taxonomy.FORMAT_TOPICS | {taxonomy.UNCLASSIFIED}
    train_idx = [i for i, t in enumerate(title_topics) if t not in skip]
    target_idx = [i for i, t in enumerate(title_topics) if t == taxonomy.UNCLASSIFIED]
    if not train_idx or not target_idx:
        return list(title_topics), 0

    def text(i):
        return clues[i]['question'] + ' ' + clues[i]['answer']

    vec = TfidfVectorizer(sublinear_tf=True, min_df=2, ngram_range=(1, 2),
                          max_features=MAX_FEATURES)
    X = vec.fit_transform(text(i) for i in train_idx)
    model = SGDClassifier(loss='log_loss', alpha=1e-7, max_iter=60,
                          tol=1e-5, random_state=0)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', ConvergenceWarning)
        model.fit(X, [title_topics[i] for i in train_idx])

    proba = model.predict_proba(vec.transform(text(i) for i in target_idx))
    best = np.argmax(proba, axis=1)
    conf = proba.max(axis=1)

    out = list(title_topics)
    filled = 0
    for j, i in enumerate(target_idx):
        if conf[j] >= MIN_CONFIDENCE:
            out[i] = model.classes_[best[j]]
            filled += 1
    return out, filled
