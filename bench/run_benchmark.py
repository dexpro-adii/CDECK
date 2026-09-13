import os
import sys
import json
import numpy as np

# Configure UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

# Add backend to path so we can import detectors
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, backend_dir)
from detectors.jailbreak_detector import detect_jailbreak

def load_benchmark_cases():
    cases_path = os.path.join(os.path.dirname(__file__), 'benchmark_cases.json')
    with open(cases_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_evaluation():
    cases = load_benchmark_cases()
    print(f"Loaded {len(cases)} benchmark cases from bench/benchmark_cases.json\n")

    results = []
    
    # Categorization counts
    group_stats = {
        "adversarial": {"total": 0, "detected_high": 0, "detected_medium_or_high": 0, "missed": 0},
        "in_category_benign": {"total": 0, "false_positive_high": 0, "false_positive_medium": 0, "true_negative": 0},
        "out_of_category_benign": {"total": 0, "false_positive_high": 0, "false_positive_medium": 0, "true_negative": 0}
    }

    category_stats = {}

    for item in cases:
        cid = item["id"]
        text = item["text"]
        label = item["label"]
        group = item["group"]
        cat = item["category"]

        if cat not in category_stats:
            category_stats[cat] = {
                "total": 0, "fp_high": 0, "fp_med": 0, "tp_high": 0, "tp_med": 0, "fn": 0, "tn": 0,
                "is_adversarial": (label == 1)
            }

        score, matched_cat, method, risk, matched_phrase, sim = detect_jailbreak(text)

        entry = {
            "id": cid,
            "text": text,
            "label": label,
            "group": group,
            "category": cat,
            "score": score,
            "risk": risk,
            "method": method,
            "matched_category": matched_cat,
            "similarity": sim
        }
        results.append(entry)

        group_stats[group]["total"] += 1
        category_stats[cat]["total"] += 1

        if label == 1:
            if risk == "high":
                group_stats[group]["detected_high"] += 1
                group_stats[group]["detected_medium_or_high"] += 1
                category_stats[cat]["tp_high"] += 1
                category_stats[cat]["tp_med"] += 1
            elif risk == "medium":
                group_stats[group]["detected_medium_or_high"] += 1
                category_stats[cat]["tp_med"] += 1
            else:
                group_stats[group]["missed"] += 1
                category_stats[cat]["fn"] += 1
        else:
            if risk == "high":
                group_stats[group]["false_positive_high"] += 1
                category_stats[cat]["fp_high"] += 1
            elif risk == "medium":
                group_stats[group]["false_positive_medium"] += 1
                category_stats[cat]["fp_med"] += 1
            else:
                group_stats[group]["true_negative"] += 1
                category_stats[cat]["tn"] += 1

    # Print Summary Metrics
    print("="*80)
    print("PROMPTKAVACH BENCHMARK EVALUATION REPORT")
    print("="*80)

    # 1. Adversarial Recall
    adv = group_stats["adversarial"]
    recall_high = (adv["detected_high"] / adv["total"]) * 100 if adv["total"] > 0 else 0
    recall_med_high = (adv["detected_medium_or_high"] / adv["total"]) * 100 if adv["total"] > 0 else 0
    print("\n1. ADVERSARIAL ATTACK DETECTION (RECALL)")
    print("-" * 50)
    print(f"Total Adversarial Cases              : {adv['total']}")
    print(f"Detected as HIGH Risk (Blocked)      : {adv['detected_high']} ({recall_high:.2f}%)")
    print(f"Detected as MEDIUM or HIGH Risk      : {adv['detected_medium_or_high']} ({recall_med_high:.2f}%)")
    print(f"Missed (Classified as LOW Risk)      : {adv['missed']}")

    # 2. IN-CATEGORY Benign False Positive Rate
    incat = group_stats["in_category_benign"]
    fpr_incat_high = (incat["false_positive_high"] / incat["total"]) * 100 if incat["total"] > 0 else 0
    fpr_incat_med = ((incat["false_positive_high"] + incat["false_positive_medium"]) / incat["total"]) * 100 if incat["total"] > 0 else 0
    tn_incat_rate = (incat["true_negative"] / incat["total"]) * 100 if incat["total"] > 0 else 0
    print("\n2. IN-CATEGORY BENIGN HARD NEGATIVES (FALSE-POSITIVE RATE)")
    print("-" * 50)
    print(f"Total In-Category Benign Cases       : {incat['total']}")
    print(f"Correctly Classified as LOW (TN)    : {incat['true_negative']} ({tn_incat_rate:.2f}%)")
    print(f"False Positives - HIGH Risk (Blocked): {incat['false_positive_high']} ({fpr_incat_high:.2f}%)")
    print(f"False Positives - MEDIUM Risk        : {incat['false_positive_medium']}")
    print(f"Total False-Positive Rate (High)     : {fpr_incat_high:.2f}%")
    print(f"Total False-Positive Rate (Med+High) : {fpr_incat_med:.2f}%")

    # 3. OUT-OF-CATEGORY Benign False Positive Rate (REPORTED SEPARATELY)
    outcat = group_stats["out_of_category_benign"]
    fpr_outcat_high = (outcat["false_positive_high"] / outcat["total"]) * 100 if outcat["total"] > 0 else 0
    fpr_outcat_med = ((outcat["false_positive_high"] + outcat["false_positive_medium"]) / outcat["total"]) * 100 if outcat["total"] > 0 else 0
    tn_outcat_rate = (outcat["true_negative"] / outcat["total"]) * 100 if outcat["total"] > 0 else 0
    print("\n3. OUT-OF-CATEGORY BENIGN HARD NEGATIVES (FALSE-POSITIVE RATE - REPORTED SEPARATELY)")
    print("-" * 50)
    print(f"Total Out-of-Category Benign Cases   : {outcat['total']}")
    print(f"Correctly Classified as LOW (TN)    : {outcat['true_negative']} ({tn_outcat_rate:.2f}%)")
    print(f"False Positives - HIGH Risk (Blocked): {outcat['false_positive_high']} ({fpr_outcat_high:.2f}%)")
    print(f"False Positives - MEDIUM Risk        : {outcat['false_positive_medium']}")
    print(f"Total False-Positive Rate (High)     : {fpr_outcat_high:.2f}%")
    print(f"Total False-Positive Rate (Med+High) : {fpr_outcat_med:.2f}%")

    # 4. Overall Combined Benign Summary
    total_benign = incat["total"] + outcat["total"]
    total_fp_high = incat["false_positive_high"] + outcat["false_positive_high"]
    total_fp_med = incat["false_positive_medium"] + outcat["false_positive_medium"]
    overall_fpr_high = (total_fp_high / total_benign) * 100 if total_benign > 0 else 0
    overall_fpr_med = ((total_fp_high + total_fp_med) / total_benign) * 100 if total_benign > 0 else 0
    print("\n4. COMBINED BENIGN FALSE-POSITIVE SUMMARY")
    print("-" * 50)
    print(f"Total Combined Benign Cases          : {total_benign}")
    print(f"Overall High-Risk FPR (Blocked)      : {total_fp_high}/{total_benign} ({overall_fpr_high:.2f}%)")
    print(f"Overall Med+High FPR (Flagged)       : {total_fp_high + total_fp_med}/{total_benign} ({overall_fpr_med:.2f}%)")

    # 5. Breakdown by Category
    print("\n5. DETAILED CATEGORY-BY-CATEGORY BREAKDOWN")
    print("-" * 80)
    print(f"{'Category':<28} | {'Total':<6} | {'Passed/TN':<10} | {'FP (High)':<10} | {'FP (Med)':<10} | {'FPR (High)':<10}")
    print("-" * 80)
    for cat, stats in sorted(category_stats.items()):
        total = stats["total"]
        if stats.get("is_adversarial", False):
            # Adversarial category
            tp_high = stats["tp_high"]
            tp_med = stats["tp_med"]
            recall = (tp_med / total) * 100 if total > 0 else 0
            print(f"[ADV] {cat:<22} | {total:<6} | Blocked: {tp_high:<4} Flagged: {tp_med:<4} | Recall: {recall:.1f}%")
        else:
            tn = stats["tn"]
            fp_high = stats["fp_high"]
            fp_med = stats["fp_med"]
            fpr = (fp_med / total) * 100 if total > 0 else 0
            print(f"[BEN] {cat:<22} | {total:<6} | TN: {tn:<7} FP(H): {fp_high:<2} FP(M): {fp_med:<2} | FPR(Med+High): {fpr:.2f}%")
    print("-" * 80)

    # 6. Flagged Cases Review
    flagged = [r for r in results if (r["label"] == 0 and r["risk"] != "low") or (r["label"] == 1 and r["risk"] == "low")]
    if flagged:
        print("\n6. CASES REQUIRING ATTENTION (Mismatches):")
        print("-" * 80)
        for r in flagged:
            print(f"ID: {r['id']} | True Label: {r['label']} | Result: {r['risk']} (score: {r['score']:.4f}, method: {r['method']})")
            print(f"  Category: {r['category']} | Text: {r['text']}")
    else:
        print("\n6. ZERO MISCLASSIFICATIONS! All cases classified cleanly.")

    print("\n" + "="*80)
    return results

if __name__ == "__main__":
    run_evaluation()
