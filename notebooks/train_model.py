"""
train_model.py  —  APP-COMPATIBLE + FAST THRESHOLD TUNING
Urban Air Quality Health Risk Predictor
Features match streamlit_app.py exactly.
"""

import os, warnings, joblib, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine

from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    classification_report, roc_auc_score,
    ConfusionMatrixDisplay, precision_recall_curve
)
from xgboost import XGBClassifier
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import StratifiedKFold, cross_val_score

warnings.filterwarnings("ignore")
load_dotenv()
t0 = time.time()
def elapsed():
    return f"[{time.time()-t0:5.1f}s]"

print("🚀 APP-COMPATIBLE TRAIN SCRIPT (fast threshold)")
Path("models").mkdir(exist_ok=True)

# ── 1. LOAD DATA ──
print(f"\n{elapsed()} 📥 Loading data from MySQL...")
DB_URL = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}"
    f"@{os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}/{os.getenv('MYSQL_DB')}"
)
engine = create_engine(DB_URL)

SQL = """
SELECT
    dd.full_date, dd.year, dd.month, dd.quarter,
    dd.day_of_week, dd.is_weekend, dd.season,
    dl.state_name, f.location_id, f.aqi_value,
    f.aqi_category_num, f.defining_param
FROM fact_daily_aqi f
JOIN dim_date     dd ON f.date_id     = dd.date_id
JOIN dim_location dl ON f.location_id = dl.location_id
WHERE f.aqi_value IS NOT NULL
  AND f.aqi_category_num IS NOT NULL
  AND dd.year BETWEEN 2021 AND 2025
ORDER BY f.location_id, dd.full_date
"""
df = pd.read_sql(SQL, engine, parse_dates=["full_date"])
print(f"{elapsed()} Loaded {len(df):,} rows | {df.full_date.min().date()} → {df.full_date.max().date()}")

# ── 2. FEATURE ENGINEERING ──
print(f"\n{elapsed()} 🔧 Engineering features...")
df = df.sort_values(["location_id","full_date"]).reset_index(drop=True)

for lag in [1,2,3,7,14]:
    df[f"aqi_lag{lag}"] = df.groupby("location_id")["aqi_value"].shift(lag)

for window in [7,14,30]:
    df[f"aqi_roll{window}"] = (
        df.groupby("location_id")["aqi_value"]
        .transform(lambda x: x.shift(1).rolling(window, min_periods=3).mean())
    )

df["aqi_roll7_std"] = (
    df.groupby("location_id")["aqi_value"]
    .transform(lambda x: x.shift(1).rolling(7, min_periods=3).std())
)

df["aqi_trend_7d"]  = df["aqi_lag1"] - df["aqi_lag7"]
df["aqi_trend_14d"] = df["aqi_lag1"] - df["aqi_lag14"]
df["aqi_change_1d"] = df["aqi_lag1"] - df["aqi_lag2"]
df["aqi_change_7d"] = df["aqi_lag7"] - df["aqi_lag14"]
df["aqi_ratio_7d"]  = df["aqi_lag1"] / (df["aqi_lag7"] + 1e-5)
df["aqi_ratio_30d"] = df["aqi_lag1"] / (df["aqi_roll30"] + 1e-5)

# Target = tomorrow's risk
df["target"] = (df["aqi_category_num"] >= 2).astype(int)
df["target"] = df.groupby("location_id")["target"].shift(-1)

required = [
    "target","aqi_lag1","aqi_lag2","aqi_lag3","aqi_lag7","aqi_lag14",
    "aqi_roll7","aqi_roll14","aqi_roll30","aqi_roll7_std","aqi_trend_7d"
]
df.dropna(subset=required, inplace=True)
df["target"] = df["target"].astype(int)
print(f"{elapsed()} Rows: {len(df):,}  |  At-Risk: {df.target.mean():.2%}")

# Categorical encoding
le_state = LabelEncoder(); le_season = LabelEncoder(); le_param = LabelEncoder()
df["state_enc"] = le_state.fit_transform(df["state_name"].fillna("Unknown"))
df["season_enc"] = le_season.fit_transform(df["season"].fillna("Unknown"))
df["param_enc"] = le_param.fit_transform(df["defining_param"].fillna("Unknown"))

# Cyclical time
df["month_sin"] = np.sin(2*np.pi*df["month"]/12)
df["month_cos"] = np.cos(2*np.pi*df["month"]/12)
df["dow_sin"]   = np.sin(2*np.pi*df["day_of_week"]/7)
df["dow_cos"]   = np.cos(2*np.pi*df["day_of_week"]/7)
df["week_of_year"] = df["full_date"].dt.isocalendar().week.astype(int)
df["week_sin"]  = np.sin(2*np.pi*df["week_of_year"]/52)
df["week_cos"]  = np.cos(2*np.pi*df["week_of_year"]/52)
df["day_of_year"] = df["full_date"].dt.dayofyear

# State-season interaction
df["state_season"] = df["state_enc"].astype(str) + "_" + df["season_enc"].astype(str)
le_state_season = LabelEncoder()
df["state_season_enc"] = le_state_season.fit_transform(df["state_season"])

FEATURES = [
    "year","month","quarter","day_of_week","day_of_year",
    "is_weekend","season_enc","state_enc","param_enc",
    "month_sin","month_cos","dow_sin","dow_cos",
    "week_sin","week_cos","state_season_enc",
    "aqi_lag1","aqi_lag2","aqi_lag3","aqi_lag7","aqi_lag14",
    "aqi_roll7","aqi_roll14","aqi_roll30",
    "aqi_roll7_std",
    "aqi_trend_7d","aqi_trend_14d",
    "aqi_change_1d","aqi_change_7d",
    "aqi_ratio_7d","aqi_ratio_30d",
]

X = df[FEATURES]
y = df["target"]

# ── 3. TRAIN/TEST SPLIT ──
train_mask = df["year"] < 2025
X_train, X_test = X[train_mask], X[~train_mask]
y_train, y_test = y[train_mask], y[~train_mask]
print(f"{elapsed()} Train: {len(X_train):,} | Test: {len(X_test):,}")

# ── 4. SMOTE ──
print(f"\n{elapsed()} ⚗️ Applying SMOTE ...")
smote = SMOTE(random_state=42, k_neighbors=3)
X_train, y_train = smote.fit_resample(X_train, y_train)
print(f"After SMOTE — At-Risk: {y_train.mean():.2%}")

scale_pos_weight = (y_train==0).sum() / max((y_train==1).sum(), 1)

# ── 5. TRAIN ──
print(f"\n{elapsed()} 🤖 Training XGBoost...")
model = XGBClassifier(
    n_estimators=400, max_depth=6, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=scale_pos_weight,
    eval_metric="aucpr", early_stopping_rounds=30,
    tree_method="hist", random_state=42, n_jobs=-1, verbosity=0
)
model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=25)
best_n = model.best_iteration
print(f"{elapsed()} Best iteration: {best_n}")

# ── 6. CV (small sample, fast) ──
print(f"\n{elapsed()} 📐 Cross-validation (25k sample, 2 folds)...")
from sklearn.model_selection import KFold
n_sample = min(25000, len(X_train))
sample_idx = np.random.RandomState(42).choice(len(X_train), size=n_sample, replace=False)
X_cv_small = X_train.iloc[sample_idx]
y_cv_small = y_train.iloc[sample_idx]
cv = KFold(n_splits=2, shuffle=True, random_state=42)
model_cv = XGBClassifier(n_estimators=best_n, max_depth=6, learning_rate=0.05,
                          scale_pos_weight=scale_pos_weight,
                          tree_method="hist", random_state=42, n_jobs=-1, verbosity=0)
cv_scores = cross_val_score(model_cv, X_cv_small, y_cv_small, cv=cv, scoring="roc_auc", n_jobs=-1)
print(f"{elapsed()} 2-Fold CV ROC-AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

# ── 7. THRESHOLD TUNING (vectorized, instant) ──
print(f"\n{elapsed()} 🎯 Tuning threshold ...")
y_proba = model.predict_proba(X_test)[:,1]
precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)

# Compute F2 directly from precision/recall (beta=2)
beta2 = 2**2
f2_scores = (1+beta2) * (precisions * recalls) / (beta2 * precisions + recalls + 1e-10)

# Restrict to recall >= 0.5
target_recall = 0.5
valid = np.where(recalls >= target_recall)[0]
if len(valid) == 0:
    best_idx = np.argmax(recalls)
else:
    best_idx = valid[np.argmax(f2_scores[valid])]

best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.0
y_pred = (y_proba >= best_threshold).astype(int)
print(f"Threshold: {best_threshold:.3f} | Recall: {recalls[best_idx]:.3f} | Precision: {precisions[best_idx]:.3f} | F2: {f2_scores[best_idx]:.3f}")
print(classification_report(y_test, y_pred, target_names=["Safe","At-Risk"]))

# ── 8. SAVE ──
print(f"\n{elapsed()} 💾 Saving model artifacts...")
joblib.dump({
    "model": model,
    "features": FEATURES,
    "best_threshold": best_threshold,
    "le_state": le_state,
    "le_season": le_season,
    "le_param": le_param,
    "le_state_season": le_state_season,
    "state_classes": list(le_state.classes_),
    "season_classes": list(le_season.classes_),
    "param_classes": list(le_param.classes_),
    "best_n_estimators": best_n,
    "cv_auc_mean": float(cv_scores.mean()),
    "test_roc_auc": float(roc_auc_score(y_test, y_proba)),
}, "models/aqi_risk_model.pkl")
print(f"{elapsed()} ✅ Saved models/aqi_risk_model.pkl")
print("\n✅ Ready for: streamlit run app/streamlit_app.py")