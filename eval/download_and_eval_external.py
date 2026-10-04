import os
import sys
import json
import urllib.request
import time
import math
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
backend_dir = os.path.join(repo_root, 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from detectors.jailbreak_detector import detect_jailbreak, JAILBREAK_EXAMPLES

def wilson_ci(k: int, n: int, confidence: float = 0.95):
    if n <= 0:
        return 0.0, 0.0, 0.0, "0.0% [0.0%, 0.0%]"
    p_hat = k / n
    z = 1.959963984540054
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))
    lower = max(0.0, center - margin) * 100.0
    upper = min(1.0, center + margin) * 100.0
    rate = p_hat * 100.0
    return round(rate, 2), round(lower, 2), round(upper, 2), f"{rate:.1f}% [{lower:.1f}%, {upper:.1f}%]"

def fetch_deepset_split(split: str, total_rows: int):
    rows = []
    offset = 0
    limit = 100
    while offset < total_rows:
        url = f"https://datasets-server.huggingface.co/rows?dataset=deepset%2Fprompt-injections&config=default&split={split}&offset={offset}&limit={limit}"
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            batch = data.get("rows", [])
            if not batch:
                break
            for r in batch:
                row_data = r.get("row", {})
                rows.append({
                    "text": row_data.get("text", "").strip(),
                    "label": int(row_data.get("label", 0)),  # 1 = injection/attack, 0 = benign
                    "split": split
                })
            offset += len(batch)
            time.sleep(0.2)
    return rows

def check_seed_overlap(external_prompts, seed_prompts):
    norm_seeds = {s.strip().lower() for s in seed_prompts}
    overlap = []
    for item in external_prompts:
        t_norm = item["text"].strip().lower()
        if t_norm in norm_seeds:
            overlap.append(item["text"])
    return overlap

def main():
    data_path = os.path.join(repo_root, 'eval', 'data', 'external_deepset.jsonl')
    
    if os.path.exists(data_path):
        print(f"Loading cached external dataset from {data_path}...")
        dataset = []
        with open(data_path, 'r', encoding='utf-8') as f:
            for l in f:
                if l.strip():
                    dataset.append(json.loads(l))
    else:
        print("Downloading deepset/prompt-injections from Hugging Face...")
        # 546 train + 116 test = 662 rows
        train_rows = fetch_deepset_split("train", 546)
        test_rows = fetch_deepset_split("test", 116)
        dataset = train_rows + test_rows
        print(f"Downloaded {len(dataset)} prompts ({len(train_rows)} train, {len(test_rows)} test).")
        
        with open(data_path, 'w', encoding='utf-8') as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Saved to {data_path}")

    # Check for seed leakage / overlap
    overlap = check_seed_overlap(dataset, JAILBREAK_EXAMPLES)
    print(f"\nTraining Seed Overlap Check:")
    print(f"Overlap with JAILBREAK_EXAMPLES: {len(overlap)} prompts.")
    if overlap:
        print(f"Sample overlapping prompts: {overlap[:3]}")

    # Filter out overlapping prompts to guarantee zero leakage
    filtered_dataset = [d for d in dataset if d["text"].strip().lower() not in {s.strip().lower() for s in JAILBREAK_EXAMPLES}]
    print(f"Evaluating on {len(filtered_dataset)} strictly zero-overlap external prompts...")

    # Evaluation
    attacks = [d for d in filtered_dataset if d["label"] == 1]
    benign = [d for d in filtered_dataset if d["label"] == 0]
    print(f"External composition: {len(attacks)} attacks (injection), {len(benign)} benign.")

    tp_h = 0
    tp_m = 0
    fn_h = 0
    fn_m = 0

    print("Evaluating external attacks...")
    for idx, a in enumerate(attacks):
        res = detect_jailbreak(a["text"], enable_hybrid=False)
        if res.risk_level == "high":
            tp_h += 1
            tp_m += 1
        elif res.risk_level == "medium":
            fn_h += 1
            tp_m += 1
        else:
            fn_h += 1
            fn_m += 1

    fp_h = 0
    fp_m = 0
    tn_h = 0
    tn_m = 0

    print("Evaluating external benign prompts...")
    for idx, b in enumerate(benign):
        res = detect_jailbreak(b["text"], enable_hybrid=False)
        if res.risk_level == "high":
            fp_h += 1
            fp_m += 1
        elif res.risk_level == "medium":
            fp_m += 1
            tn_h += 1
        else:
            tn_h += 1
            tn_m += 1

    # Metrics computation with Wilson CIs
    rec_h, rhl, rhu, rh_str = wilson_ci(tp_h, len(attacks))
    rec_m, rfl, rfu, rf_str = wilson_ci(tp_m, len(attacks))
    fpr_h, fhl, fhu, fh_str = wilson_ci(fp_h, len(benign))
    fpr_m, fml, fmu, fm_str = wilson_ci(fp_m, len(benign))

    prec_h, phl, phu, ph_str = wilson_ci(tp_h, tp_h + fp_h)
    prec_m, pml, pmu, pm_str = wilson_ci(tp_m, tp_m + fp_m)

    f1_h = round((2 * prec_h * rec_h) / (prec_h + rec_h), 2) if (prec_h + rec_h) > 0 else 0.0
    f1_m = round((2 * prec_m * rec_m) / (prec_m + rec_m), 2) if (prec_m + rec_m) > 0 else 0.0

    results = {
        "dataset_name": "deepset/prompt-injections",
        "total_prompts": len(filtered_dataset),
        "attacks_count": len(attacks),
        "benign_count": len(benign),
        "overlap_excluded_count": len(overlap),
        "high_risk_blocked": {
            "tp": tp_h, "fp": fp_h, "tn": tn_h, "fn": fn_h,
            "recall": rec_h, "recall_ci": [rhl, rhu], "recall_ci_str": rh_str,
            "precision": prec_h, "precision_ci": [phl, phu], "precision_ci_str": ph_str,
            "fpr": fpr_h, "fpr_ci": [fhl, fhu], "fpr_ci_str": fh_str,
            "f1": f1_h
        },
        "flagged_med_plus_high": {
            "tp": tp_m, "fp": fp_m, "tn": tn_m, "fn": fn_m,
            "recall": rec_m, "recall_ci": [rfl, rfu], "recall_ci_str": rf_str,
            "precision": prec_m, "precision_ci": [pml, pmu], "precision_ci_str": pm_str,
            "fpr": fpr_m, "fpr_ci": [fml, fmu], "fpr_ci_str": fm_str,
            "f1": f1_m
        }
    }

    out_json = os.path.join(repo_root, 'eval', 'results', 'external_deepset_results.json')
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    # Markdown report
    md = f"""# External Benchmark Evaluation: deepset/prompt-injections

- **Source:** Hugging Face `deepset/prompt-injections`
- **Total Prompts:** {len(filtered_dataset)} ({len(attacks)} attacks, {len(benign)} benign)
- **Overlap Excluded:** {len(overlap)} prompts matched training seeds and were removed prior to evaluation.
- **Evaluation Mode:** Strictly zero training, zero threshold tuning, offline inference only.

---

## 1. External Performance Summary

| Metric | HIGH Risk (Blocked) | FLAGGED (Med + High) |
| :--- | :---: | :---: |
| **Recall (95% CI)** | **{rh_str}** ({tp_h}/{len(attacks)}) | **{rf_str}** ({tp_m}/{len(attacks)}) |
| **False Positive Rate (95% CI)** | **{fh_str}** ({fp_h}/{len(benign)}) | **{fm_str}** ({fp_m}/{len(benign)}) |
| **Precision (95% CI)** | **{ph_str}** | **{pm_str}** |
| **F1 Score** | **{f1_h}** | **{f1_m}** |

---

## 2. Comparison with Internal Benchmark

| Benchmark | Recall @ BLOCK (95% CI) | FPR @ BLOCK (95% CI) | Recall @ FLAGGED (95% CI) | FPR @ FLAGGED (95% CI) |
| :--- | :---: | :---: | :---: | :---: |
| **Internal Test Split** | 72.1% [60.5%, 81.4%] | 2.5% [0.7%, 8.5%] | 83.8% [73.3%, 90.7%] | 8.6% [4.3%, 16.6%] |
| **deepset/prompt-injections** | **{rh_str}** | **{fh_str}** | **{rf_str}** | **{fm_str}** |

"""
    out_md = os.path.join(repo_root, 'eval', 'results', 'external_deepset_results.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write(md)

    print("\n" + "=" * 70)
    print("EXTERNAL VALIDATION RESULTS (deepset/prompt-injections)")
    print("=" * 70)
    print(f"Recall @ BLOCK:   {rh_str} (TP: {tp_h}/{len(attacks)})")
    print(f"FPR @ BLOCK:      {fh_str} (FP: {fp_h}/{len(benign)})")
    print(f"Recall @ FLAGGED: {rf_str} (TP: {tp_m}/{len(attacks)})")
    print(f"FPR @ FLAGGED:    {fm_str} (FP: {fp_m}/{len(benign)})")
    print("=" * 70)
    print(f"Saved results to: {out_json} and {out_md}")

if __name__ == "__main__":
    main()
