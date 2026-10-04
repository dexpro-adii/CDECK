"""
backend/scripts/train_stacked_scorer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Trains a calibrated stacked scorer (Logistic Regression + Platt Scaling) over
layer-level features on the DEV split only:
  - heuristic_score
  - heuristic_category (one-hot)
  - knn_similarity (top-3 mean)
  - knn_max_sim
  - classifier_prob (retrained base classifier)
  - benign_damping flag
  - is_legit_research flag
  - has_normalization & normalization_type

Determines calibrated thresholds on DEV:
  - BLOCK: lowest threshold with FPR <= 2.0%
  - WARN: lowest threshold with FPR <= 8.0%
Saves:
  - backend/models/stacked_scorer.joblib
  - backend/config/thresholds.json
"""

import os
import sys
import json
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, roc_auc_score
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from normalizer import Normalizer
from detectors.jailbreak_detector import (
    HEURISTIC_PATTERNS,
    check_heuristic,
    check_legit_heuristic,
    check_benign_context,
    normalize_text,
    JAILBREAK_EXAMPLES
)

CATEGORIES = [
    "none", "instruction_override", "system_prompt_extraction", "role_play",
    "data_exfiltration", "delimiter_break", "authority_escalation", "nested_injection",
    "credential_theft", "fake_system_message", "supply_chain_redirect", "zero_width_injection"
]

NORM_TYPES = [
    "none", "base64", "leetspeak", "spaced_letters", "rot13", "hinglish_canonical", "homoglyphs", "composite"
]

def extract_features(text: str, model: SentenceTransformer, ref_embeddings: np.ndarray, base_clf) -> np.ndarray:
    """
    Extracts fixed 1D feature vector for a given prompt string.
    Evaluates original and candidate variants through Normalizer, taking winning variant.
    """
    variants = Normalizer.generate_variants(text)
    
    # Pre-encode all variants in a batch for speed
    variant_texts = [v["text"] for v in variants]
    cleaned_texts = []
    structural_flags = []
    for vt in variant_texts:
        ct, flags = normalize_text(vt)
        cleaned_texts.append(ct)
        structural_flags.append(flags)
        
    v_embeddings = model.encode(cleaned_texts, batch_size=len(cleaned_texts), normalize_embeddings=True)
    all_sims = cosine_similarity(v_embeddings, ref_embeddings)
    v_probs = base_clf.predict_proba(v_embeddings)[:, 1]

    best_candidate_idx = 0
    best_candidate_score = -1.0
    best_h_score = 0.0
    best_h_cat = "none"

    # Evaluate each variant
    for idx, cand in enumerate(variants):
        c_text = cleaned_texts[idx]
        flags = structural_flags[idx]
        
        h_cat = flags[0] if flags else check_heuristic(c_text)
        if flags:
            h_score = 0.92
        elif h_cat:
            h_score = 0.80
        else:
            h_score = 0.0

        sims = all_sims[idx]
        top3_sim = float(np.mean(np.sort(sims)[-3:]))
        c_prob = float(v_probs[idx])
        
        # Candidate selection priority: max proxy score
        proxy = max(h_score, top3_sim, c_prob)
        if proxy > best_candidate_score:
            best_candidate_score = proxy
            best_candidate_idx = idx
            best_h_score = h_score
            best_h_cat = h_cat or "none"

    win_cand = variants[best_candidate_idx]
    win_text = cleaned_texts[best_candidate_idx]
    win_sims = all_sims[best_candidate_idx]
    win_top3 = float(np.mean(np.sort(win_sims)[-3:]))
    win_max = float(np.max(win_sims))
    win_prob = float(v_probs[best_candidate_idx])
    win_trans = win_cand["transformation"]

    benign_ctx = 1.0 if check_benign_context(win_text) else 0.0
    legit_res = 1.0 if check_legit_heuristic(win_text) else 0.0
    has_norm = 1.0 if win_trans != "none" else 0.0

    # Build feature vector
    feats = []
    # 1. Continuous signals
    feats.append(best_h_score)
    feats.append(win_top3)
    feats.append(win_max)
    feats.append(win_prob)
    feats.append(benign_ctx)
    feats.append(legit_res)
    feats.append(has_norm)

    # 2. Heuristic category one-hot
    for cat in CATEGORIES:
        feats.append(1.0 if best_h_cat == cat else 0.0)

    # 3. Normalization type one-hot
    for nt in NORM_TYPES:
        feats.append(1.0 if win_trans == nt else 0.0)

    return np.array(feats, dtype=np.float32)

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    data_dir = os.path.join(repo_root, 'eval', 'data')
    
    with open(os.path.join(data_dir, 'split.json'), 'r', encoding='utf-8') as f:
        split_data = json.load(f)

    with open(os.path.join(data_dir, 'attacks.jsonl'), 'r', encoding='utf-8') as f:
        all_attacks = {x['id']: x for x in (json.loads(l) for l in f if l.strip())}
    with open(os.path.join(data_dir, 'benign.jsonl'), 'r', encoding='utf-8') as f:
        all_benign = {x['id']: x for x in (json.loads(l) for l in f if l.strip())}

    dev_attacks = [all_attacks[i] for i in split_data["dev"]["attack_ids"]]
    dev_benign = [all_benign[i] for i in split_data["dev"]["benign_ids"]]

    print(f"Loading DEV dataset: {len(dev_attacks)} attacks, {len(dev_benign)} benign...")

    # Load models
    model_name = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    print(f"Loading embedding model ({model_name})...")
    model = SentenceTransformer(model_name)
    
    backend_dir = os.path.join(repo_root, 'backend')
    embs_path = os.path.join(backend_dir, 'models', 'jailbreak_embeddings_multilingual.npy')
    ref_embeddings = np.load(embs_path)
    
    clf_path = os.path.join(backend_dir, 'models', 'jailbreak_classifier.joblib')
    base_clf = joblib.load(clf_path)

    print("Extracting features for DEV attacks...")
    X_att = [extract_features(a["text"], model, ref_embeddings, base_clf) for a in dev_attacks]
    y_att = [1] * len(dev_attacks)

    print("Extracting features for DEV benign...")
    X_ben = [extract_features(b["text"], model, ref_embeddings, base_clf) for b in dev_benign]
    y_ben = [0] * len(dev_benign)

    X = np.vstack([X_att, X_ben])
    y = np.array(y_att + y_ben)
    print(f"Feature matrix shape: {X.shape}, Labels: {len(y)} ({np.sum(y==1)} attacks, {np.sum(y==0)} benign)")

    # Cross-validation for threshold selection & calibration
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    base_stacker = LogisticRegression(C=2.0, max_iter=1000, random_state=42, class_weight='balanced')
    
    # Use cross_val_predict with method='predict_proba' to get out-of-fold calibrated probabilities
    oof_probs = cross_val_predict(base_stacker, X, y, cv=skf, method='predict_proba')[:, 1]
    cv_auc = roc_auc_score(y, oof_probs)
    print(f"\n5-Fold Out-Of-Fold CV ROC-AUC: {cv_auc:.4f}")

    # Threshold selection on out-of-fold DEV probabilities
    att_probs = oof_probs[y == 1]
    ben_probs = oof_probs[y == 0]

    # Target: BLOCK FPR <= 2%, WARN FPR <= 8%
    # Sweep thresholds from 0.01 to 0.99
    thresholds_grid = np.linspace(0.01, 0.99, 99)
    best_block_thresh = 0.85
    best_warn_thresh = 0.50

    # Find lowest threshold keeping FPR <= 2.0% for BLOCK
    candidate_block = [t for t in thresholds_grid if (np.sum(ben_probs >= t) / len(ben_probs)) * 100.0 <= 2.0]
    if candidate_block:
        best_block_thresh = float(round(candidate_block[0], 2))

    # Find lowest threshold keeping FPR <= 8.0% for WARN
    candidate_warn = [t for t in thresholds_grid if (np.sum(ben_probs >= t) / len(ben_probs)) * 100.0 <= 8.0]
    if candidate_warn:
        best_warn_thresh = float(round(candidate_warn[0], 2))

    block_recall = float((np.sum(att_probs >= best_block_thresh) / len(att_probs)) * 100.0)
    block_fpr = float((np.sum(ben_probs >= best_block_thresh) / len(ben_probs)) * 100.0)
    warn_recall = float((np.sum(att_probs >= best_warn_thresh) / len(att_probs)) * 100.0)
    warn_fpr = float((np.sum(ben_probs >= best_warn_thresh) / len(ben_probs)) * 100.0)

    print(f"\nCalibrated Threshold Selection on DEV (Cross-Validated):")
    print(f"  BLOCK Threshold: {best_block_thresh:.2f} -> Recall: {block_recall:.2f}%, FPR: {block_fpr:.2f}%")
    print(f"  WARN Threshold : {best_warn_thresh:.2f} -> Recall: {warn_recall:.2f}%, FPR: {warn_fpr:.2f}%")

    # Fit final calibrated model on all DEV data
    calibrated_stacker = CalibratedClassifierCV(base_stacker, method='sigmoid', cv=skf)
    calibrated_stacker.fit(X, y)

    # Save model
    model_out = os.path.join(backend_dir, 'models', 'stacked_scorer.joblib')
    joblib.dump(calibrated_stacker, model_out)
    print(f"\nSaved calibrated stacked scorer to {model_out}")

    # Save configuration thresholds
    config_dir = os.path.join(backend_dir, 'config')
    os.makedirs(config_dir, exist_ok=True)
    config_out = os.path.join(config_dir, 'thresholds.json')
    
    thresholds_config = {
        "block_threshold": best_block_thresh,
        "warn_threshold": best_warn_thresh,
        "calibrated_fpr_block": block_fpr,
        "calibrated_recall_block": block_recall,
        "calibrated_fpr_warn": warn_fpr,
        "calibrated_recall_warn": warn_recall,
        "cv_roc_auc": round(cv_auc, 4),
        "target_fpr_block_max": 2.0,
        "target_fpr_warn_max": 8.0,
        "model_version": "paraphrase-multilingual-MiniLM-L12-v2",
        "timestamp": "2026-10-04"
    }
    with open(config_out, 'w', encoding='utf-8') as f:
        json.dump(thresholds_config, f, indent=2)
    print(f"Saved threshold configuration to {config_out}")

if __name__ == '__main__':
    main()
