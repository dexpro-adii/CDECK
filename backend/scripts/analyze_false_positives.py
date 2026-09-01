import os
import sys
import numpy as np
import joblib
from datasets import load_dataset
from sklearn.model_selection import train_test_split
from sentence_transformers import SentenceTransformer

# Add backend directory to sys path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from detectors.jailbreak_detector import JAILBREAK_EXAMPLES, detect_jailbreak

MAX_SAMPLES_PER_CLASS = 20000
MAX_WORDS = 200

# Existing examples to deduplicate against
existing_examples_set = set(p.strip().lower() for p in JAILBREAK_EXAMPLES)
seen_prompts = set(existing_examples_set)

def is_valid_prompt(text):
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if len(text.split()) > MAX_WORDS:
        return False
    text_lower = text.lower()
    if text_lower in seen_prompts:
        return False
    seen_prompts.add(text_lower)
    return True

print("Loading datasets in streaming mode...")
jailbreak_ds = load_dataset("youbin2014/JailbreakDB", streaming=True, split='jailbreak')
regular_ds = load_dataset("youbin2014/JailbreakDB", streaming=True, split='regular')

texts = []
labels = []

print("Collecting jailbreak samples...")
jb_count = 0
for item in jailbreak_ds:
    prompt = item.get("user_prompt", "")
    if is_valid_prompt(prompt):
        texts.append(prompt)
        labels.append(1)
        jb_count += 1
        if jb_count >= MAX_SAMPLES_PER_CLASS:
            break

print("Collecting regular samples...")
reg_count = 0
for item in regular_ds:
    prompt = item.get("user_prompt", "")
    if is_valid_prompt(prompt):
        texts.append(prompt)
        labels.append(0)
        reg_count += 1
        if reg_count >= MAX_SAMPLES_PER_CLASS:
            break

print(f"Collected {jb_count} jailbreak and {reg_count} regular samples.")

# Train/Val/Test split: 80/10/10
# First split 80/20
X_train_txt, X_temp_txt, y_train_txt, y_temp_txt = train_test_split(texts, labels, test_size=0.2, random_state=42, stratify=labels)
# Then split the 20% into 10/10
X_val_txt, X_test_txt, y_val_txt, y_test_txt = train_test_split(X_temp_txt, y_temp_txt, test_size=0.5, random_state=42, stratify=y_temp_txt)

models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models'))
model_path = os.path.join(models_dir, 'jailbreak_classifier.joblib')
X_test_path = os.path.join(models_dir, 'X_test.npy')
y_test_path = os.path.join(models_dir, 'y_test.npy')

print("Loading saved classifier and embeddings...")
clf = joblib.load(model_path)
X_test = np.load(X_test_path)
y_test = np.load(y_test_path)

y_pred = clf.predict(X_test)

# Find false positives: y_test == 0 (regular) and y_pred == 1 (predicted jailbreak)
fp_indices = [i for i in range(len(y_test)) if y_test[i] == 0 and y_pred[i] == 1]

print(f"Total False Positives in test set: {len(fp_indices)}")

# Verify mapping with embedding similarity
model = SentenceTransformer('all-MiniLM-L6-v2')
test_emb = model.encode([X_test_txt[fp_indices[0]]])[0]
saved_emb = X_test[fp_indices[0]]
sim = np.dot(test_emb, saved_emb) / (np.linalg.norm(test_emb) * np.linalg.norm(saved_emb))
print(f"Embedding similarity check for mapping: {sim:.4f} (should be ~1.0)")

if sim < 0.99:
    print("Warning: Text mapping might be incorrect. Embeddings do not match.")

print("\n--- Testing Full Pipeline on 20 False Positives ---")

num_to_test = min(20, len(fp_indices))
tested_indices = fp_indices[:num_to_test]
fp_texts = [X_test_txt[i] for i in tested_indices]

# Run through full pipeline (MAX strategy is default)
os.environ["COMBINATION_STRATEGY"] = "max"

medium_high_count = 0
low_count = 0

for i, text in enumerate(fp_texts):
    score, matched_category, method, risk_level, final_matched_phrase, final_matched_phrase_similarity = detect_jailbreak(text)
    print(f"\nFP #{i+1}:")
    print(f"Text: {text}")
    print(f"Pipeline Result -> Risk: {risk_level.upper()}, Score: {score:.3f}, Method: {method}, Category: {matched_category}")
    if risk_level in ["medium", "high"]:
        medium_high_count += 1
    else:
        low_count += 1

print("\n--- Summary ---")
print(f"Total false positives evaluated: {num_to_test}")
print(f"Still flagged as medium/high by full pipeline: {medium_high_count}")
print(f"Correctly overruled to low risk by full pipeline: {low_count}")
