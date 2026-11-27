"""Compares several classifiers for the burnout risk label and saves the evidence.

Run from the csv folder (with the .venv active):
    python compare_models.py

It prints the results and also saves them to model_comparison.txt.

Important limitation (say this in the defense): the burnout label is built from
rules on these same columns (see train_model.py). So the scores below show how
well each model learns those rules, not how well it predicts real-world burnout.
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")

# ---- 1. Same data preparation as train_model.py ----
df = pd.read_csv("student_sleep_patterns.csv")
features = [
    "Sleep_Duration",
    "Study_Hours",
    "Screen_Time",
    "Caffeine_Intake",
    "Sleep_Quality",
]
data = df[features].copy()

np.random.seed(42)
data["Temperature_C"] = np.round(np.random.uniform(26.0, 35.0, size=len(data)), 1)


def calculate_burnout(row):
    """Same rules as train_model.py (keep the two in sync)."""
    score = 0
    if row["Sleep_Duration"] < 5.5:
        score += 2
    elif row["Sleep_Duration"] < 7.0:
        score += 1

    if row["Sleep_Quality"] <= 4:
        score += 2
    elif row["Sleep_Quality"] <= 6:
        score += 1

    if row["Temperature_C"] >= 32.0 and row["Sleep_Duration"] < 6.5:
        score += 1

    if row["Study_Hours"] > 6.0 or row["Caffeine_Intake"] >= 3:
        score += 1

    if score >= 4:
        return 2
    elif score >= 2:
        return 1
    return 0


data["Burnout_Risk"] = data.apply(calculate_burnout, axis=1)
X = data[features + ["Temperature_C"]]
y = data["Burnout_Risk"]

lines = []


def out(text=""):
    print(text)
    lines.append(text)


names = {0: "Low", 1: "Moderate", 2: "High"}
counts = y.value_counts().sort_index()
out("Class counts: " + ", ".join(f"{names[k]}={v}" for k, v in counts.items()))
out(f"Rows: {len(data)}")
out()

# ---- 2. Models to compare ----
models = {
    "Baseline (always most common class)": DummyClassifier(strategy="most_frequent"),
    "Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
    "Decision Tree (depth 5)": DecisionTreeClassifier(max_depth=5, random_state=42),
    "Random Forest (100 trees)": RandomForestClassifier(n_estimators=100, random_state=42),
}

n_splits = max(2, min(5, int(counts.min())))
cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
scoring = ["accuracy", "precision_macro", "recall_macro", "f1_macro"]

out(f"{n_splits}-fold cross-validation (mean of the folds)")
out(f"{'Model':38} {'Accuracy':>9} {'Precision':>10} {'Recall':>8} {'F1':>6}")
results = {}
for name, model in models.items():
    r = cross_validate(model, X, y, cv=cv, scoring=scoring)
    results[name] = {m: r[f"test_{m}"].mean() for m in scoring}
    s = results[name]
    out(f"{name:38} {s['accuracy']:9.2f} {s['precision_macro']:10.2f} {s['recall_macro']:8.2f} {s['f1_macro']:6.2f}")

out()
out("Precision, recall and F1 are macro averages (each risk level counts equally).")

# ---- 3. Best model: confusion matrix on a held-out test split ----
best_name = max(
    (n for n in results if not n.startswith("Baseline")),
    key=lambda n: results[n]["f1_macro"],
)
out()
out(f"Best model by F1: {best_name}")

stratify = y if counts.min() >= 2 else None
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=stratify
)
best = models[best_name]
best.fit(X_train, y_train)
pred = best.predict(X_test)

labels = sorted(y.unique())
out()
out("Confusion matrix on the 20% test split (rows = actual, columns = predicted)")
out("          " + " ".join(f"{names[k]:>9}" for k in labels))
for k, row in zip(labels, confusion_matrix(y_test, pred, labels=labels)):
    out(f"{names[k]:9} " + " ".join(f"{v:9d}" for v in row))

out()
out(classification_report(y_test, pred, labels=labels,
                          target_names=[names[k] for k in labels], zero_division=0))

# ---- 4. Which inputs matter most (global explanation) ----
forest = RandomForestClassifier(n_estimators=100, random_state=42).fit(X, y)
out("Random Forest feature importance (how much each input drives the prediction)")
for col, imp in sorted(zip(X.columns, forest.feature_importances_), key=lambda t: -t[1]):
    out(f"  {col:18} {imp:.2f}")

out()
out("Limitation: labels come from rules on these same inputs and the temperature column is")
out("simulated, so these scores measure how well a model learns the rules, not real burnout.")

with open("model_comparison.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\nSaved to model_comparison.txt")
