"""Optional advisory models (scikit-learn). Synthetic training data comes from ml/data.py."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline


class ThresholdCalibrator:
    """Predicts the background unique-demand per evaluation window for a cell; proposes ΔT."""

    def __init__(self, k: float = 1.5, seed: int = 0):
        self.k = k
        self.m = GradientBoostingRegressor(random_state=seed, n_estimators=150, max_depth=3)

    def fit(self, X, y):
        self.m.fit(np.asarray(X), np.asarray(y))
        return self

    def propose_delta(self, x, t_base: float) -> float:
        bg = float(self.m.predict(np.asarray([x]))[0])
        return self.k * bg + 5.0 - t_base


class IndependenceEstimator:
    def __init__(self, seed: int = 0):
        self.m = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=seed)

    def fit(self, X, y):
        self.m.fit(np.asarray(X), np.asarray(y))
        return self

    def prob_duplicate(self, X):
        return self.m.predict_proba(np.asarray(X))[:, 1]


class SaliencyProposer:
    def __init__(self, seed: int = 0):
        self.m = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2),
                               LogisticRegression(max_iter=2000, random_state=seed))

    def fit(self, texts, y):
        self.m.fit(texts, y)
        return self

    def prob(self, texts):
        return self.m.predict_proba(texts)[:, 1]
