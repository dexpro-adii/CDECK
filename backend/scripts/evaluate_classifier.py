import os
import joblib
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
from collections import Counter

# File paths
models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models'))
model_path = os.path.join(models_dir, 'jailbreak_classifier.joblib')
X_test_path = os.path.join(models_dir, 'X_test.npy')
y_test_path = os.path.join(models_dir, 'y_test.npy')

if not os.path.exists(X_test_path) or not os.path.exists(y_test_path):
    print("Test splits not found. Please run train_classifier.py first.")
    exit(1)

# Load real model and real test data
print("Loading saved classifier...")
clf = joblib.load(model_path)

print("Loading saved test splits...")
X_test = np.load(X_test_path)
y_test = np.load(y_test_path)

print("\n--- Genuine Classifier Evaluation ---")
# Class balance
balance = Counter(y_test)
print(f"Test Set Total: {len(y_test)}")
print(f"  Benign (0): {balance[0]}")
print(f"  Jailbreak (1): {balance[1]}")

# Predictions
print("\nPredicting on Test Set...")
y_pred = clf.predict(X_test)

# Real Metrics
accuracy = accuracy_score(y_test, y_pred)
precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average='binary')

print("\n--- Actual Scikit-Learn Metric Returns ---")
print(f"Accuracy:  {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall:    {recall:.4f}")
print(f"F1 Score:  {f1:.4f}")

# Confusion Matrix
cm = confusion_matrix(y_test, y_pred)
tn, fp, fn, tp = cm.ravel()
print("\n--- Real Confusion Matrix ---")
print(f"True Negatives (Correctly Benign):  {tn}")
print(f"False Positives (Falsely Flagged):  {fp}")
print(f"False Negatives (Missed Jailbreak): {fn}")
print(f"True Positives (Caught Jailbreak):  {tp}")
