import json
import os
import sys

from detectors.jailbreak_detector import detect_jailbreak
from detectors.pii_detector import detect_pii

def load_data(filepath):
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line))
    return data

def main():
    dataset_path = "prompt_guard_dataset.jsonl"
    if not os.path.exists(dataset_path):
        print(f"Dataset not found at {dataset_path}")
        sys.exit(1)
        
    records = load_data(dataset_path)
    print(f"Loaded {len(records)} records.")
    
    results = {
        "jailbreak_obvious": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
        "jailbreak_creative": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
        "hard_negative": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
        "educational_security": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
        "indirect_injection": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
        "pii_redaction": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
        "pii_benign": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
        "benign": {"total": 0, "correct": 0, "incorrect": 0, "errors": []},
    }
    
    for i, record in enumerate(records):
        cat = record["category"]
        text = record["text"]
        
        if cat not in results:
            continue
            
        results[cat]["total"] += 1
        
        if cat in ["jailbreak_obvious", "jailbreak_creative", "indirect_injection"]:
            # Expecting medium/high
            score, jb_cat, jb_method, risk_level, matched_phrase, sim = detect_jailbreak(text)
            if risk_level in ["medium", "high"]:
                results[cat]["correct"] += 1
            else:
                results[cat]["incorrect"] += 1
                if len(results[cat]["errors"]) < 5:
                    results[cat]["errors"].append(text)
                    
        elif cat in ["hard_negative", "educational_security", "benign"]:
            # Expecting low
            score, jb_cat, jb_method, risk_level, matched_phrase, sim = detect_jailbreak(text)
            if risk_level == "low":
                results[cat]["correct"] += 1
            else:
                results[cat]["incorrect"] += 1
                if len(results[cat]["errors"]) < 5:
                    results[cat]["errors"].append(f"[{risk_level.upper()}] {text}")
                    
        elif cat == "pii_redaction":
            # Expecting PII found
            pii_found = detect_pii(text)
            if len(pii_found) > 0:
                results[cat]["correct"] += 1
            else:
                results[cat]["incorrect"] += 1
                if len(results[cat]["errors"]) < 5:
                    results[cat]["errors"].append(text)
                    
        elif cat == "pii_benign":
            # Expecting NO PII found
            pii_found = detect_pii(text)
            if len(pii_found) == 0:
                results[cat]["correct"] += 1
            else:
                results[cat]["incorrect"] += 1
                if len(results[cat]["errors"]) < 5:
                    results[cat]["errors"].append(f"[Found: {pii_found}] {text}")
        
        if (i+1) % 500 == 0:
            print(f"Processed {i+1} records...")

    print("\n" + "="*50)
    print("FINAL VALIDATION RESULTS")
    print("="*50)
    
    for cat, data in results.items():
        print(f"\n--- {cat.upper()} ---")
        print(f"Total: {data['total']}")
        if data['total'] > 0:
            print(f"Correct: {data['correct']} ({(data['correct']/data['total']*100):.1f}%)")
        print(f"Incorrect: {data['incorrect']}")
        
        if data["incorrect"] > 0:
            print("Examples of incorrect classifications:")
            for err in data["errors"]:
                print(f"  - {err.strip()}")

if __name__ == "__main__":
    main()
