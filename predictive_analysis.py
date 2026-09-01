#Will a given customer be a subscriber (Yes) or not (No)?

"""
predictive_analysis.py
 
Extension analysis, run and validated against the project's real cleaned
dataset (output_data.xlsx, 3,900 rows). Two additions on top of the
descriptive SQL analysis:
 
  PART 1 — Logistic Regression: what predicts subscription?
  PART 2 — KMeans Clustering: data-driven customer segments
 
IMPORTANT — read before reusing this script on a refreshed dataset:
Two columns, `gender` and `discount_applied`, were tested first and
dropped from the final model. In this dataset:
  - 100% of subscribers (1,053 / 1,053) have discount_applied = "Yes"
  - 100% of subscribers (1,053 / 1,053) are gender = "Male"
Both are exact, zero-exception splits — that is not a plausible behavioral
signal, it's almost certainly an artifact of how this (widely-used,
synthetic) dataset was generated. Leaving them in produces a model that
looks impressive (ROC AUC ~0.89) but is reporting a data artifact, not a
business insight. ALWAYS run the leakage check below before trusting a
feature's importance score, especially on a public/synthetic dataset.
"""
 
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
 
 
# ============================================================================
# STEP 0 — Leakage check (run this before trusting ANY feature importance)
# ============================================================================
 
def check_near_perfect_separation(df: pd.DataFrame, target_col: str, candidate_cols: list, threshold: float = 0.98):
    """
    Flags categorical features where one category almost entirely determines
    the target — a strong sign of leakage or a synthetic-data artifact rather
    than genuine signal. Prints a crosstab for anything that trips the
    threshold so you can eyeball it before deciding whether to exclude it.
    """
    target = df[target_col]
    flagged = []
    for col in candidate_cols:
        ct = pd.crosstab(df[col], target, normalize="index")
        max_purity = ct.max(axis=1).max()
        if max_purity >= threshold:
            flagged.append(col)
            print(f"⚠️  '{col}' is {max_purity:.1%} pure for at least one category — likely leakage/artifact:")
            print(pd.crosstab(df[col], target))
            print()
    if not flagged:
        print("No near-perfect separators found among:", candidate_cols)
    return flagged
 
 
# ============================================================================
# PART 1 — Logistic Regression: what predicts subscription?
# ============================================================================
 
def run_subscription_model(df: pd.DataFrame, exclude: list = None) -> pd.DataFrame:
    """
    Predicts subscription_status (Yes/No) from behavioral + demographic
    features, excluding any columns passed in `exclude` (use this for
    columns flagged by check_near_perfect_separation).
    """
    exclude = exclude or []
    model_df = df.copy()
    model_df["target"] = model_df["subscription_status"].map({"Yes": 1, "No": 0})
 
    numeric_features = [c for c in ["age", "previous_purchases", "purchase_amount", "review_rating", "purchase_frequency_days"] if c not in exclude]
    categorical_features = [c for c in ["gender", "category", "discount_applied", "shipping_type", "payment_method", "season"] if c not in exclude]
 
    X = model_df[numeric_features + categorical_features].copy()
    y = model_df["target"]
 
    for col in categorical_features:
        X[col] = LabelEncoder().fit_transform(X[col].astype(str))
 
    scaler = StandardScaler()
    X[numeric_features] = scaler.fit_transform(X[numeric_features])
 
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
 
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_train, y_train)
 
    y_pred = clf.predict(X_test)
    y_proba = clf.predict_proba(X_test)[:, 1]
 
    print("=== Subscription Prediction — Model Performance ===")
    print(classification_report(y_test, y_pred, target_names=["Non-subscriber", "Subscriber"], zero_division=0))
    print(f"ROC AUC: {roc_auc_score(y_test, y_proba):.3f}  (0.50 = no better than random)")
 
    importance = pd.DataFrame({
        "feature": X.columns,
        "coefficient": clf.coef_[0],
        "odds_ratio": np.exp(clf.coef_[0]),
    }).sort_values("odds_ratio", ascending=False)
 
    print("\n=== Feature Effect on Subscription Odds ===")
    print(importance.to_string(index=False))
 
    return importance
 
 
# ============================================================================
# PART 2 — KMeans Clustering: data-driven customer segments
# ============================================================================
 
def run_customer_clustering(df: pd.DataFrame, cluster_features: list, k_range=range(2, 7)) -> pd.DataFrame:
    """
    Clusters customers on the given numeric features and profiles the result.
    Note: purchase_frequency_days ranges 7-365 while previous_purchases and
    purchase_amount range roughly 1-50 / $20-100 — even after scaling, cadence
    tends to dominate the split if included alongside the other two. Run with
    ['previous_purchases', 'purchase_amount'] for a spend/frequency view, and
    separately with purchase_frequency_days included, to see both.
    """
    X = df[cluster_features].copy()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
 
    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        scores[k] = silhouette_score(X_scaled, labels)
 
    best_k = max(scores, key=scores.get)
    print(f"=== Cluster Selection (features: {cluster_features}) ===\nSilhouette scores by k: { {k: round(v,3) for k,v in scores.items()} }")
    print(f"Selected k = {best_k}")
 
    km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    df = df.copy()
    df["segment"] = km_final.fit_predict(X_scaled)
 
    profile = (
        df.groupby("segment")[cluster_features]
        .mean()
        .assign(customer_count=df.groupby("segment").size())
        .sort_values(cluster_features[-1], ascending=False)
    )
 
    print("\n=== Segment Profiles (mean values) ===")
    print(profile.to_string())
 
    return profile
 
 
if __name__ == "__main__":
    df = pd.read_excel("data/processed/output_data.xlsx")  # adjust path as needed
 
    print("############  STEP 0: LEAKAGE CHECK  ############")
    leaky = check_near_perfect_separation(
        df, "subscription_status", ["gender", "discount_applied", "category", "shipping_type", "payment_method", "season"]
    )
 
    print("\n############  PART 1: SUBSCRIPTION MODEL (leaky features excluded)  ############")
    run_subscription_model(df, exclude=leaky)
 
    print("\n############  PART 2a: CLUSTERING on purchases + spend  ############")
    run_customer_clustering(df, ["previous_purchases", "purchase_amount"])
 
    print("\n############  PART 2b: CLUSTERING on purchases + spend + cadence  ############")
    run_customer_clustering(df, ["previous_purchases", "purchase_amount", "purchase_frequency_days"])