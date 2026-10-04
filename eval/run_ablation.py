import os
import sys
import json
import re
from unittest.mock import patch

# Ensure backend and repo root on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
backend_dir = os.path.join(repo_root, 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from normalizer import Normalizer
import detectors.jailbreak_detector as jb_mod
from detectors.jailbreak_detector import detect_jailbreak, THRESHOLDS

def load_dev_data():
    with open(os.path.join(repo_root, 'eval', 'data', 'split.json'), 'r', encoding='utf-8') as f:
        split_data = json.load(f)

    dev_attack_ids = set(split_data["dev"]["attack_ids"])
    dev_benign_ids = set(split_data["dev"]["benign_ids"])

    attacks = []
    with open(os.path.join(repo_root, 'eval', 'data', 'attacks.jsonl'), 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item["id"] in dev_attack_ids:
                    attacks.append(item)

    benign = []
    with open(os.path.join(repo_root, 'eval', 'data', 'benign.jsonl'), 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item["id"] in dev_benign_ids:
                    benign.append(item)

    return attacks, benign

def evaluate_config(name: str, attacks: list, benign: list):
    tp_high = 0
    tp_flagged = 0
    fn_high = 0
    fn_flagged = 0

    deva_tp_high = 0
    deva_total = 0

    obf_tp_high = 0
    obf_total = 0

    fp_high = 0
    fp_flagged = 0
    tn_high = 0
    tn_flagged = 0

    for a in attacks:
        text = a["text"]
        lang = a.get("language", "EN")
        obf = a.get("obfuscation", "none")

        res = detect_jailbreak(text, enable_hybrid=False)
        is_high = res.risk_level == "high"
        is_flagged = res.risk_level in ("high", "medium")

        if is_high:
            tp_high += 1
        else:
            fn_high += 1

        if is_flagged:
            tp_flagged += 1
        else:
            fn_flagged += 1

        if lang.lower() == "hi_deva":
            deva_total += 1
            if is_high:
                deva_tp_high += 1

        if obf != "none":
            obf_total += 1
            if is_high:
                obf_tp_high += 1

    for b in benign:
        text = b["text"]
        res = detect_jailbreak(text, enable_hybrid=False)
        is_high = res.risk_level == "high"
        is_flagged = res.risk_level in ("high", "medium")

        if is_high:
            fp_high += 1
        else:
            tn_high += 1

        if is_flagged:
            fp_flagged += 1
        else:
            tn_flagged += 1

    rec_high = round((tp_high / len(attacks)) * 100.0, 2)
    rec_flg = round((tp_flagged / len(attacks)) * 100.0, 2)
    fpr_high = round((fp_high / len(benign)) * 100.0, 2)
    fpr_flg = round((fp_flagged / len(benign)) * 100.0, 2)
    deva_rec = round((deva_tp_high / deva_total) * 100.0, 2) if deva_total else 0.0
    obf_rec = round((obf_tp_high / obf_total) * 100.0, 2) if obf_total else 0.0

    return {
        "config": name,
        "recall_high": rec_high,
        "recall_flagged": rec_flg,
        "fpr_high": fpr_high,
        "fpr_flagged": fpr_flg,
        "deva_recall_high": deva_rec,
        "obf_recall_high": obf_rec
    }

def main():
    attacks, benign = load_dev_data()
    print(f"Loaded DEV split: {len(attacks)} attacks, {len(benign)} benign.")

    results = []

    # 1. Full Pipeline (Step 2.4)
    print("Evaluating: Full Pipeline...")
    res_full = evaluate_config("Full Pipeline (Step 2.4)", attacks, benign)
    results.append(res_full)

    # 2. Without Normalizer
    print("Evaluating: Without Normalizer...")
    with patch.object(Normalizer, "generate_variants", side_effect=lambda t: [{"text": t, "transformation": "none"}]):
        res_no_norm = evaluate_config("w/o Normalizer (Raw text)", attacks, benign)
        results.append(res_no_norm)

    # 3. Without Devanagari Regexes
    print("Evaluating: Without Devanagari Regexes...")
    orig_heuristics = {cat: list(pats) for cat, pats in jb_mod.HEURISTIC_PATTERNS.items()}
    try:
        no_deva_heuristics = {}
        for cat, pats in orig_heuristics.items():
            no_deva_heuristics[cat] = [p for p in pats if not re.search(r"[\u0900-\u097F]", p)]
        jb_mod.HEURISTIC_PATTERNS = no_deva_heuristics
        res_no_deva = evaluate_config("w/o Devanagari Regexes", attacks, benign)
        results.append(res_no_deva)
    finally:
        jb_mod.HEURISTIC_PATTERNS = orig_heuristics

    # 4. Without Base ML Classifier
    print("Evaluating: Without Base ML Classifier...")
    orig_clf = jb_mod.classifier
    try:
        jb_mod.classifier = None
        res_no_clf = evaluate_config("w/o Base Classifier", attacks, benign)
        results.append(res_no_clf)
    finally:
        jb_mod.classifier = orig_clf

    # 5. Without Stacked Scorer (raw MAX combination)
    print("Evaluating: Without Stacked Scorer (Legacy MAX)...")
    orig_stacker = jb_mod.stacked_scorer
    try:
        jb_mod.stacked_scorer = None
        res_no_stack = evaluate_config("w/o Stacked Scorer (Legacy MAX)", attacks, benign)
        results.append(res_no_stack)
    finally:
        jb_mod.stacked_scorer = orig_stacker

    print("\n" + "=" * 95)
    print(f"{'Configuration':<35} | {'Rec@HIGH':<9} | {'Rec@FLG':<9} | {'FPR@HIGH':<9} | {'Deva@HIGH':<10} | {'Obf@HIGH':<9}")
    print("-" * 95)
    for r in results:
        print(f"{r['config']:<35} | {r['recall_high']:<8}% | {r['recall_flagged']:<8}% | {r['fpr_high']:<8}% | {r['deva_recall_high']:<9}% | {r['obf_recall_high']:<8}%")
    print("=" * 95)

    out_path = os.path.join(repo_root, 'eval', 'results', 'dev_ablation.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved ablation results to {out_path}")

if __name__ == "__main__":
    main()
