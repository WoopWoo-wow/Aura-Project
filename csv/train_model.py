import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import joblib

# 1. Load the Kaggle CSV (update filename if needed)
df = pd.read_csv('student_sleep_patterns.csv')

# 2. Keep only the core columns we need
features = [
    'Sleep_Duration',
    'Study_Hours',
    'Screen_Time',
    'Caffeine_Intake',
    'Sleep_Quality'
]
df_clean = df[features].copy()

# 3. Enrich with Davao City Temperature (°C) for System Integration alignment
np.random.seed(42)
df_clean['Temperature_C'] = np.round(np.random.uniform(26.0, 35.0, size=len(df_clean)), 1)

# 4. Create the Target Variable: Burnout_Risk (0 = Low, 1 = Moderate, 2 = High)
def calculate_burnout(row: pd.Series) -> int:
    score = 0
    if row['Sleep_Duration'] < 5.5:
        score += 2
    elif row['Sleep_Duration'] < 7.0:
        score += 1
        
    if row['Sleep_Quality'] <= 4:
        score += 2
    elif row['Sleep_Quality'] <= 6:
        score += 1
        
    if row['Temperature_C'] >= 32.0 and row['Sleep_Duration'] < 6.5:
        score += 1  # Heat multiplier on tired students
        
    if row['Study_Hours'] > 6.0 or row['Caffeine_Intake'] >= 3:
        score += 1

    if score >= 4:
        return 2  # High Burnout Risk
    elif score >= 2:
        return 1  # Moderate Burnout Risk
    return 0      # Low Burnout Risk

df_clean['Burnout_Risk'] = df_clean.apply(calculate_burnout, axis=1)

# 5. Train the Random Forest ModelS
X = df_clean[features + ['Temperature_C']]
y = df_clean['Burnout_Risk']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# 6. Check accuracy and save the trained model
preds = model.predict(X_test)
print(f"Model Accuracy: {accuracy_score(y_test, preds) * 100:.2f}%")

joblib.dump(model, 'burnout_model.pkl')
print("Saved trained model as 'burnout_model.pkl'!")
