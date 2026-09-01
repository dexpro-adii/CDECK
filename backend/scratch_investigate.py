from datasets import load_dataset
import json

try:
    print("Loading jailbreak split...")
    ds_jb = load_dataset("youbin2014/JailbreakDB", streaming=True, split='jailbreak')
    first_few_jb = []
    for i, item in enumerate(ds_jb):
        first_few_jb.append(item)
        if i >= 1: break
    print(json.dumps(first_few_jb, indent=2))
    
    print("Loading regular split...")
    ds_reg = load_dataset("youbin2014/JailbreakDB", streaming=True, split='regular')
    first_few_reg = []
    for i, item in enumerate(ds_reg):
        first_few_reg.append(item)
        if i >= 1: break
    print(json.dumps(first_few_reg, indent=2))
except Exception as e:
    print(f"Error: {e}")
