# Audit Note: The MAX Combination Strategy and the 0.74 Classifier Clamp

## 1. What the MAX Combination Does
In `backend/detectors/jailbreak_detector.py`, the legacy decision logic combines signals across three distinct layers (regex heuristics, embedding cosine similarity, and logistic regression classifier) using a conditional `max(...)` rule:

```python
if heuristic_category and embedding_flagged and clf_flagged:
    score = max(0.9, max_sim, clf_prob)
    risk_level = "high"
elif heuristic_category:
    score = 0.8
    risk_level = "high"
elif embedding_flagged:
    score = max_sim
    risk_level = "high"
elif clf_flagged:
    score = min(clf_prob, 0.74)
    risk_level = "medium"
elif max_sim >= 0.56 or clf_prob >= 0.55:
    score = max(max_sim, clf_prob)
    risk_level = "medium"
else:
    score = max(max_sim, clf_prob)
    risk_level = "low"
```

### Flaws of the `MAX` Strategy:
1. **Ignores Joint Weak Evidence (False Negatives):**
   If embedding top-3 similarity is `0.54` (sub-threshold) and classifier probability is `0.53` (sub-threshold), `max(0.54, 0.53) = 0.54`. The system classifies the prompt as `LOW` risk, despite two completely independent semantic detectors both observing strong attack characteristics.
2. **Ignores Contradictory Evidence (False Positives):**
   If a harmless benign prompt contains an innocent trigger word (e.g. "What are the rules of cricket?"), the classifier or a loose regex spikes to `0.80`. The embedding layer may correctly show a tiny similarity of `0.20` to actual jailbreaks, but `max()` completely ignores this negative evidence and flags the user.
3. **Uncalibrated Layer Magnitudes:**
   Comparing an uncalibrated regex score (`0.80`), a bounded cosine similarity metric (`0.50 - 0.75`), and an uncalibrated linear model log-odds output on a single `max()` scale is mathematically ungrounded.

---

## 2. What the 0.74 Clamp Does
In the legacy pipeline:
```python
elif clf_flagged:
    score = min(clf_prob, 0.74)
    risk_level = "medium"
```
The threshold for a `HIGH` (blocking) verdict was originally hardcoded at `0.75`. The previous developers realized that their logistic regression classifier had extreme false positives on harmless prompts containing words like `"system"`, `"rule"`, `"instruction"`, or telephone numbers. 

Rather than retraining the classifier with hard negatives or calibrating its probability distribution, they applied an ad-hoc band-aid: **they clamped any verdict originating solely from the classifier to a maximum of 0.74**.

### Consequences of the Clamp:
- The classifier alone was **permanently crippled** from ever blocking an attack (`HIGH` risk), even when 99.9% confident.
- It produced a visible artifact in evaluation and production where dozens of inputs were artificially pegged at exactly `0.740`.
- It failed to solve the underlying problem: benign prompts still got falsely flagged as `MEDIUM` (12-16% FPR @ Flagged).

---

## 3. The Solution: Stacked Scorer & Hard-Negative Retraining (Step 2.4)
1. **Retrain the Base Classifier with Hard Negatives:**
   Separate training dataset with recipes, cricket rules, laws of motion, system architecture, programming questions, and Indian customer service queries to suppress trigger-word false positives.
2. **Feature Extraction for Stacking:**
   Extract a feature vector for each candidate:
   - `heuristic_score`: Continuous score (0.0 to 1.0)
   - `heuristic_category_idx`: One-hot encoded category
   - `knn_similarity`: Top-3 mean cosine similarity against jailbreak vectors
   - `classifier_prob`: Retrained base classifier probability
   - `benign_damping_flag`: Binary indicator (1 if customer support / harmless context detected)
   - `normalization_flags`: Active transformations (base64, leetspeak, spaced letters, homoglyphs)
3. **Calibrated Stacked Model (Logistic Regression + Platt Scaling):**
   Trained strictly on the DEV split with cross-validation to learn optimal weighting between layers.
4. **Empirically Selected Thresholds Stored in Config:**
   - `BLOCK`: Lowest threshold achieving $\le 2\%$ FPR on DEV.
   - `WARN`: Lowest threshold achieving $\le 8\%$ FPR on DEV.
   Thresholds saved to `backend/config/thresholds.json`.
