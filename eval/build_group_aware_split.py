import os
import sys
import json
import random
from collections import defaultdict

# Set deterministic seed
random.seed(42)

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
data_dir = os.path.join(repo_root, 'eval', 'data')

def main():
    with open(os.path.join(data_dir, 'attacks.jsonl'), 'r', encoding='utf-8') as f:
        attacks = [json.loads(l) for l in f if l.strip()]

    with open(os.path.join(data_dir, 'benign.jsonl'), 'r', encoding='utf-8') as f:
        benign = [json.loads(l) for l in f if l.strip()]

    with open(os.path.join(data_dir, 'paraphrases.jsonl'), 'r', encoding='utf-8') as f:
        paraphrases = [json.loads(l) for l in f if l.strip()]

    print(f"Loaded: {len(attacks)} attacks, {len(benign)} benign, {len(paraphrases)} paraphrases.")

    # 1. Group paraphrases by core_id and match with original attack in attacks.jsonl
    core_to_paras = defaultdict(list)
    core_text_to_cid = {}
    for p in paraphrases:
        cid = p["core_id"]
        pid = p["paraphrase_id"]
        orig_text = p["original_text"].strip()
        core_to_paras[cid].append(pid)
        core_text_to_cid[orig_text] = cid

    # Group attacks into family groups
    # An attack that matches a core paraphrase belongs to group cid.
    # Otherwise, it forms its own singleton group.
    groups = defaultdict(lambda: {"attack_ids": [], "paraphrase_ids": [], "language": "en", "category": "none"})

    for a in attacks:
        t = a["text"].strip()
        aid = a["id"]
        lang = a.get("language", "en")
        cat = a.get("category", "none")
        if t in core_text_to_cid:
            cid = core_text_to_cid[t]
            groups[cid]["attack_ids"].append(aid)
            groups[cid]["paraphrase_ids"] = core_to_paras[cid]
            groups[cid]["language"] = lang
            groups[cid]["category"] = cat
        else:
            # Singleton group
            groups[aid]["attack_ids"].append(aid)
            groups[aid]["language"] = lang
            groups[aid]["category"] = cat

    print(f"Formed {len(groups)} distinct attack groups (including {len(core_to_paras)} multi-item core families).")

    # Stratified split by (language, category)
    strata = defaultdict(list)
    for gid, gdata in groups.items():
        key = (gdata["language"], gdata["category"])
        strata[key].append((gid, gdata))

    dev_attack_ids = []
    test_attack_ids = []
    dev_para_ids = []
    test_para_ids = []

    for key, group_list in sorted(strata.items()):
        random.shuffle(group_list)
        n = len(group_list)
        n_dev = max(1, int(round(n * 0.70))) if n > 1 else (1 if random.random() < 0.70 else 0)
        
        dev_groups = group_list[:n_dev]
        test_groups = group_list[n_dev:]

        for gid, gdata in dev_groups:
            dev_attack_ids.extend(gdata["attack_ids"])
            dev_para_ids.extend(gdata["paraphrase_ids"])

        for gid, gdata in test_groups:
            test_attack_ids.extend(gdata["attack_ids"])
            test_para_ids.extend(gdata["paraphrase_ids"])

    # Split Benign prompts stratified by language & category
    benign_strata = defaultdict(list)
    for b in benign:
        lang = b.get("language", "en")
        cat = b.get("category", "none")
        benign_strata[(lang, cat)].append(b["id"])

    dev_benign_ids = []
    test_benign_ids = []
    for key, bids in sorted(benign_strata.items()):
        random.shuffle(bids)
        n = len(bids)
        n_dev = max(1, int(round(n * 0.70))) if n > 1 else (1 if random.random() < 0.70 else 0)
        dev_benign_ids.extend(bids[:n_dev])
        test_benign_ids.extend(bids[n_dev:])

    # Deduplicate and sort
    dev_attack_ids = sorted(list(set(dev_attack_ids)))
    test_attack_ids = sorted(list(set(test_attack_ids)))
    dev_para_ids = sorted(list(set(dev_para_ids)))
    test_para_ids = sorted(list(set(test_para_ids)))
    dev_benign_ids = sorted(list(set(dev_benign_ids)))
    test_benign_ids = sorted(list(set(test_benign_ids)))

    # Verify zero overlap between dev and test
    assert len(set(dev_attack_ids) & set(test_attack_ids)) == 0, "Attack overlap!"
    assert len(set(dev_para_ids) & set(test_para_ids)) == 0, "Paraphrase overlap!"
    assert len(set(dev_benign_ids) & set(test_benign_ids)) == 0, "Benign overlap!"

    # Verify group-awareness: for every core attack, all its paraphrases are strictly in the same split!
    for p in paraphrases:
        cid = p["core_id"]
        pid = p["paraphrase_id"]
        orig_text = p["original_text"].strip()
        # Find corresponding attack id if any
        matching_att = [a["id"] for a in attacks if a["text"].strip() == orig_text]
        if matching_att:
            aid = matching_att[0]
            p_split = "dev" if pid in dev_para_ids else "test"
            a_split = "dev" if aid in dev_attack_ids else "test"
            assert p_split == a_split, f"Group-aware violation for {cid}: attack {aid} in {a_split}, paraphrase {pid} in {p_split}"

    print("VERIFIED: 100% GROUP-AWARE SPLIT. Zero cross-split leakage between attacks and paraphrases!")
    print(f"DEV Split : {len(dev_attack_ids)} attacks ({len(dev_attack_ids)/len(attacks)*100:.1f}%), {len(dev_benign_ids)} benign, {len(dev_para_ids)} paraphrases ({len(dev_para_ids)/len(paraphrases)*100:.1f}%)")
    print(f"TEST Split: {len(test_attack_ids)} attacks ({len(test_attack_ids)/len(attacks)*100:.1f}%), {len(test_benign_ids)} benign, {len(test_para_ids)} paraphrases ({len(test_para_ids)/len(paraphrases)*100:.1f}%)")

    split_obj = {
        "description": "Group-aware 70/30 stratified train/test split. Core attacks and all paraphrases strictly partitioned together with zero cross-split leakage.",
        "random_seed": 42,
        "dev": {
            "attack_ids": dev_attack_ids,
            "benign_ids": dev_benign_ids,
            "paraphrase_ids": dev_para_ids
        },
        "test": {
            "attack_ids": test_attack_ids,
            "benign_ids": test_benign_ids,
            "paraphrase_ids": test_para_ids
        }
    }

    out_file = os.path.join(data_dir, 'split.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(split_obj, f, indent=2)
    print(f"Successfully saved group-aware split to {out_file}")

if __name__ == "__main__":
    main()
