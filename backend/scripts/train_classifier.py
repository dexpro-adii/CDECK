import os
import sys
import json
import numpy as np
from datasets import load_dataset
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, precision_recall_fscore_support
import joblib
from collections import Counter

# Add backend directory to sys path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from detectors.jailbreak_detector import JAILBREAK_EXAMPLES

try:
    from langdetect import detect
except ImportError:
    print("langdetect not installed, skipping advanced language detection.")
    def detect(text): return "unknown"

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
languages = []

print("Collecting jailbreak samples...")
jb_count = 0
for item in jailbreak_ds:
    prompt = item.get("user_prompt", "")
    if is_valid_prompt(prompt):
        texts.append(prompt)
        labels.append(1)
        # sample language for 10% to speed up
        if jb_count % 10 == 0:
            try:
                languages.append(detect(prompt))
            except:
                pass
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
        if reg_count % 10 == 0:
            try:
                languages.append(detect(prompt))
            except:
                pass
        reg_count += 1
        if reg_count >= MAX_SAMPLES_PER_CLASS:
            break

print(f"Collected {jb_count} jailbreak and {reg_count} regular samples.")

# Language stats
lang_counts = Counter(languages)
total_lang_samples = sum(lang_counts.values())
print("\nLanguage Composition (Sampled):")
for lang, count in lang_counts.most_common(5):
    print(f"  {lang}: {count/total_lang_samples*100:.1f}%")

print("\nLoading sentence-transformers model...")
model = SentenceTransformer('all-MiniLM-L6-v2')

print("Computing embeddings (this may take a few minutes)...")
# batch size can be large on CPU, all-MiniLM is small
embeddings = model.encode(texts, batch_size=256, show_progress_bar=True)

# Train/Val/Test split: 80/10/10
# First split 80/20
X_train, X_temp, y_train, y_temp = train_test_split(embeddings, labels, test_size=0.2, random_state=42, stratify=labels)
# Then split the 20% into 10/10
X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp)

print(f"\nData splits:")
print(f"  Train: {len(X_train)} samples")
print(f"  Val:   {len(X_val)} samples")
print(f"  Test:  {len(X_test)} samples")

print("\nTraining Logistic Regression classifier...")
clf = LogisticRegression(max_iter=1000, random_state=42)
clf.fit(X_train, y_train)

# Validate
val_acc = clf.score(X_val, y_val)
print(f"Validation Accuracy: {val_acc:.4f}")

# Test
print("\nEvaluating on Test Set:")
y_pred = clf.predict(X_test)
precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average='binary')
print(f"  Precision: {precision:.4f}")
print(f"  Recall:    {recall:.4f}")
print(f"  F1 Score:  {f1:.4f}")

print("\nDetailed Test Classification Report:")
print(classification_report(y_test, y_pred, target_names=["Regular", "Jailbreak"]))

models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models'))
os.makedirs(models_dir, exist_ok=True)
model_path = os.path.join(models_dir, 'jailbreak_classifier.joblib')
joblib.dump(clf, model_path)

# Persist test splits to disk for genuine evaluation
np.save(os.path.join(models_dir, 'X_test.npy'), X_test)
np.save(os.path.join(models_dir, 'y_test.npy'), y_test)

print(f"\nModel saved to {model_path}")
print(f"Test splits saved to X_test.npy and y_test.npy in {models_dir}")
