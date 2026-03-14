
#%%
# ============================================================
# Repeated-Sales TOM
# Keep TOM_days for both listings in each pair to check with external data
# Less aggressive ZIP dropping
# ============================================================

import os
import numpy as np
import pandas as pd
import statsmodels.api as sm
from collections import defaultdict, deque

# -----------------------------
# Settings
# -----------------------------
dta_file   = "edit file path here"
out_dir    = "edit file path here"
base_year  = 2015
base_month = 1

# cleaning / trimming
MAX_TOM_DAYS         = 365
MAX_GAP_MONTHS       = 120
MIN_GAP_MONTHS       = 1

# This part can cause difference when different people construct the index
MIN_PAIRS_PER_ZIP    = 15
MIN_CONNECTED_MONTHS = 6

DY_TRIM_LO           = 0.005
DY_TRIM_HI           = 0.995
WEIGHT_LO_Q          = 0.01
WEIGHT_HI_Q          = 0.99

os.makedirs(out_dir, exist_ok=True)

if not os.path.exists(dta_file):
    raise FileNotFoundError(f"Input .dta not found: {dta_file}")

#%%
# -----------------------------
# Read data
# -----------------------------
usecols = [
    "TOM_days",
    "CLIP",
    "year",
    "month",
    "LISTING_DATE",
    "OFF_MARKET_DATE",
    "ZIP"
]
df = pd.read_stata(dta_file, columns=usecols)

# -----------------------------
# Basic cleaning
# -----------------------------
df = df.dropna(subset=["TOM_days", "CLIP", "year", "month"]).copy()
df["TOM_days"] = pd.to_numeric(df["TOM_days"], errors="coerce")
df = df.dropna(subset=["TOM_days"]).copy()

df = df[(df["TOM_days"] >= 0) & (df["TOM_days"] <= MAX_TOM_DAYS)].copy()

df["year"] = df["year"].astype(int)
df["month"] = df["month"].astype(int)

# tm index
start_year = int(df["year"].min())
df["tm"] = (df["year"] - start_year) * 12 + (df["month"] - 1)
df["tm"] = df["tm"].astype(int)

# ZIP cleaning
zip_raw = df["ZIP"].astype("string").str.strip()
df["zipnum"] = zip_raw.str.extract(r"(\d{5})", expand=False)

# keep observations even if ZIP is temporarily missing;
# we will recover ZIP from property-level dominant ZIP when possible
df["log_tom"] = np.log1p(df["TOM_days"].astype(float))

# -----------------------------
# Helper: safe mode
# -----------------------------
def first_mode(s):
    s = s.dropna()
    if len(s) == 0:
        return pd.NA
    m = s.mode()
    if len(m) == 0:
        return pd.NA
    return m.iloc[0]

# -----------------------------
# Collapse duplicates within property-month
# Keep one record per CLIP x tm
# Use median TOM within month
# -----------------------------
gcols = ["CLIP", "tm"]

collapsed = (
    df.groupby(gcols, as_index=False)
      .agg(
          year=("year", "first"),
          month=("month", "first"),
          log_tom=("log_tom", "median"),
          TOM_days=("TOM_days", "median"),
          zipnum=("zipnum", first_mode),
          n_rows=("CLIP", "size"),
          n_zip=("zipnum", lambda s: s.dropna().nunique())
      )
)

# -----------------------------
# Property-level dominant ZIP
# This helps rescue properties with occasional ZIP inconsistencies
# -----------------------------
prop_zip = (
    collapsed.groupby("CLIP", as_index=False)
             .agg(prop_zip=("zipnum", first_mode),
                  n_months=("tm", "size"))
)

collapsed = collapsed.merge(prop_zip, on="CLIP", how="left")

# fill missing month ZIP with property-level dominant ZIP
collapsed["zipnum"] = collapsed["zipnum"].fillna(collapsed["prop_zip"])

# if still missing ZIP, we cannot use that observation for ZIP-specific index
collapsed = collapsed.dropna(subset=["zipnum"]).copy()

#%%
# -----------------------------
# Build adjacent repeat pairs
# Assign each pair to property-level dominant ZIP
# This is less aggressive than requiring exact month-to-month ZIP equality
# -----------------------------
pairs_list = []

collapsed = collapsed.sort_values(["CLIP", "tm"]).reset_index(drop=True)

for pid, g in collapsed.groupby("CLIP", sort=False):
    if len(g) < 2:
        continue

    g = g.sort_values("tm").reset_index(drop=True)
    pair_zip = g["prop_zip"].dropna()
    if len(pair_zip) == 0:
        continue
    pair_zip = first_mode(pair_zip)

    for j in range(len(g) - 1):
        s0 = g.iloc[j]
        s1 = g.iloc[j + 1]

        t0 = int(s0["tm"])
        t1 = int(s1["tm"])
        gap = t1 - t0

        if gap < MIN_GAP_MONTHS or gap > MAX_GAP_MONTHS:
            continue

        dy = float(s1["log_tom"] - s0["log_tom"])

        pairs_list.append({
            "pid": pid,
            "zipnum": pair_zip,
            "t0": t0,
            "t1": t1,
            "dy": dy,
            "gap": gap,
            "TOM_days_0": float(s0["TOM_days"]),
            "TOM_days_1": float(s1["TOM_days"]),
            "year0": int(s0["year"]),
            "month0": int(s0["month"]),
            "year1": int(s1["year"]),
            "month1": int(s1["month"]),
        })

pairs = pd.DataFrame(pairs_list)

if pairs.empty:
    raise ValueError("No repeat-sale pairs constructed after cleaning.")

# -----------------------------
# Trim extreme dy globally
# -----------------------------
lo = pairs["dy"].quantile(DY_TRIM_LO)
hi = pairs["dy"].quantile(DY_TRIM_HI)
pairs = pairs[(pairs["dy"] >= lo) & (pairs["dy"] <= hi)].copy()

pairs["t0"] = pairs["t0"].astype(int)
pairs["t1"] = pairs["t1"].astype(int)
pairs["gap"] = pairs["gap"].astype(int)
pairs["dy"] = pairs["dy"].astype(float)
pairs["TOM_days_0"] = pairs["TOM_days_0"].astype(float)
pairs["TOM_days_1"] = pairs["TOM_days_1"].astype(float)

# Metadata
base_tm = int((base_year - start_year) * 12 + (base_month - 1))
T = int(collapsed["tm"].max() + 1)

if not (0 <= base_tm < T):
    raise ValueError(
        f"base_tm out of range: base_tm={base_tm}, T={T}, start_year={start_year}"
    )

# Save revised pair file
pairs_path = os.path.join(out_dir, "tom_repeat_pairs_revised.dta")
meta_path  = os.path.join(out_dir, "tom_repeat_meta_revised.dta")

pairs[
    [
        "pid", "zipnum", "t0", "t1", "dy", "gap",
        "TOM_days_0", "TOM_days_1",
        "year0", "month0", "year1", "month1"
    ]
].to_stata(pairs_path, write_index=False)

pd.DataFrame({
    "T": [T],
    "base_tm": [base_tm],
    "start_year": [start_year]
}).to_stata(meta_path, write_index=False)

print("Wrote:", pairs_path)
print("Wrote:", meta_path)
print("Pairs:", len(pairs), "| Unique pid:", pairs["pid"].nunique())

# ============================================================
# Revised ZIP-specific repeated-sales TOM index
# ============================================================

pairs = pd.read_stata(pairs_path)
meta  = pd.read_stata(meta_path)

T          = int(meta.loc[0, "T"])
base_tm    = int(meta.loc[0, "base_tm"])
start_year = int(meta.loc[0, "start_year"])

pairs = pairs.dropna(subset=["pid", "zipnum", "t0", "t1", "dy", "gap"]).copy()
pairs["t0"]  = pairs["t0"].astype(int)
pairs["t1"]  = pairs["t1"].astype(int)
pairs["gap"] = pairs["gap"].astype(int)
pairs["dy"]  = pairs["dy"].astype(float)

pairs = pairs[
    (pairs["t0"] >= 0) &
    (pairs["t1"] >= 0) &
    (pairs["t0"] < T) &
    (pairs["t1"] < T) &
    (pairs["gap"] > 0)
].copy()

if len(pairs) == 0:
    raise ValueError("No valid pairs after cleaning.")

# time-dummy mapping
col_tms = [k for k in range(T) if k != base_tm]
k_map = {tm: j for j, tm in enumerate(col_tms)}
K = T - 1

def build_design(t0_arr, t1_arr, T, base_tm, k_map):
    n = len(t0_arr)
    X = np.zeros((n, T - 1), dtype=float)
    for i in range(n):
        if t1_arr[i] != base_tm:
            X[i, k_map[t1_arr[i]]] = 1.0
        if t0_arr[i] != base_tm:
            X[i, k_map[t0_arr[i]]] = -1.0
    return X

def connected_months_from_base(t0_arr, t1_arr, base_tm):
    graph = defaultdict(set)
    for a, b in zip(t0_arr, t1_arr):
        graph[int(a)].add(int(b))
        graph[int(b)].add(int(a))

    seen = set([base_tm])
    q = deque([base_tm])

    while q:
        u = q.popleft()
        for v in graph[u]:
            if v not in seen:
                seen.add(v)
                q.append(v)
    return seen

# -----------------------------
# 1) pooled first-stage OLS for variance model
# -----------------------------
X_pool = build_design(
    pairs["t0"].to_numpy(),
    pairs["t1"].to_numpy(),
    T=T,
    base_tm=base_tm,
    k_map=k_map
)
y_pool = pairs["dy"].to_numpy(dtype=float)

beta_pool = np.linalg.lstsq(X_pool, y_pool, rcond=None)[0]
resid_pool = y_pool - X_pool @ beta_pool
resid2_pool = resid_pool ** 2

Z_pool = sm.add_constant(pairs["gap"].to_numpy(dtype=float))
var_fit = sm.OLS(resid2_pool, Z_pool).fit()
sig2hat_pool = var_fit.predict(Z_pool)

positive_sig = sig2hat_pool[sig2hat_pool > 0]
if len(positive_sig) == 0:
    sig2hat_pool = np.repeat(np.nanmedian(resid2_pool), len(sig2hat_pool))
else:
    floor_val = np.nanpercentile(positive_sig, 5)
    sig2hat_pool = np.maximum(sig2hat_pool, floor_val)

w_pool = 1.0 / sig2hat_pool

w_lo = np.quantile(w_pool, WEIGHT_LO_Q)
w_hi = np.quantile(w_pool, WEIGHT_HI_Q)
w_pool = np.clip(w_pool, w_lo, w_hi)

pairs["w"] = w_pool

# -----------------------------
# 2) ZIP-level estimation with connectivity checks
# -----------------------------
rows_out = []

# diagnostics
zip_stats = []

for zipnum, g in pairs.groupby("zipnum", sort=False):
    n = len(g)

    reason = "kept"

    if n < MIN_PAIRS_PER_ZIP:
        zip_stats.append({"zipnum": zipnum, "n_pairs": n, "status": "dropped_few_pairs"})
        continue

    t0 = g["t0"].to_numpy(dtype=int)
    t1 = g["t1"].to_numpy(dtype=int)
    y  = g["dy"].to_numpy(dtype=float)
    w  = g["w"].to_numpy(dtype=float)

    connected = connected_months_from_base(t0, t1, base_tm)
    if len(connected) < MIN_CONNECTED_MONTHS:
        zip_stats.append({
            "zipnum": zipnum,
            "n_pairs": n,
            "status": "dropped_few_connected_months",
            "n_connected_months": len(connected)
        })
        continue

    keep = np.array([(a in connected) and (b in connected) for a, b in zip(t0, t1)])
    if keep.sum() < MIN_PAIRS_PER_ZIP:
        zip_stats.append({
            "zipnum": zipnum,
            "n_pairs": n,
            "status": "dropped_few_pairs_in_component",
            "n_connected_pairs": int(keep.sum())
        })
        continue

    t0c = t0[keep]
    t1c = t1[keep]
    yc  = y[keep]
    wc  = w[keep]

    Xz = build_design(t0c, t1c, T=T, base_tm=base_tm, k_map=k_map)

    active_tms = sorted([tm for tm in connected if tm != base_tm])
    active_cols = [k_map[tm] for tm in active_tms]
    Xz = Xz[:, active_cols]

    if Xz.shape[1] == 0:
        zip_stats.append({"zipnum": zipnum, "n_pairs": n, "status": "dropped_no_active_cols"})
        continue

    rank_x = np.linalg.matrix_rank(Xz)

    # relaxed rank check
    if rank_x < min(3, Xz.shape[1]):
        zip_stats.append({
            "zipnum": zipnum,
            "n_pairs": n,
            "status": "dropped_low_rank",
            "rank_x": int(rank_x)
        })
        continue

    W = np.sqrt(wc)
    beta = np.linalg.lstsq(Xz * W[:, None], yc * W, rcond=None)[0]

    delta = np.full(T, np.nan, dtype=float)
    delta[base_tm] = 0.0

    for j, tm in enumerate(active_tms):
        delta[tm] = beta[j]

    tom_index = np.where(np.isnan(delta), np.nan, 100.0 * np.exp(delta))

    month_support = defaultdict(int)
    for a, b in zip(t0c, t1c):
        month_support[int(a)] += 1
        month_support[int(b)] += 1

    for tm in range(T):
        rows_out.append({
            "zipnum": zipnum,
            "tm": int(tm),
            "year": int(start_year + tm // 12),
            "month": int((tm % 12) + 1),
            "delta": float(delta[tm]) if not np.isnan(delta[tm]) else np.nan,
            "tom_index": float(tom_index[tm]) if not np.isnan(tom_index[tm]) else np.nan,
            "n_pairs_zip": int(n),
            "n_pairs_connected": int(keep.sum()),
            "month_support": int(month_support.get(tm, 0)),
            "rank_x": int(rank_x),
            "n_connected_months": int(len(connected)),
        })

    zip_stats.append({
        "zipnum": zipnum,
        "n_pairs": n,
        "status": "kept",
        "n_connected_pairs": int(keep.sum()),
        "n_connected_months": int(len(connected)),
        "rank_x": int(rank_x)
    })

zip_month = pd.DataFrame(rows_out)
zip_diag  = pd.DataFrame(zip_stats)

out_dta      = os.path.join(out_dir, "zip_month_tom_index_python_revised.dta")
out_csv      = os.path.join(out_dir, "zip_month_tom_index_python_revised.csv")
diag_csv     = os.path.join(out_dir, "zip_drop_diagnostics_revised.csv")
diag_dta     = os.path.join(out_dir, "zip_drop_diagnostics_revised.dta")

zip_month.to_stata(out_dta, write_index=False)
zip_month.to_csv(out_csv, index=False)

zip_diag.to_csv(diag_csv, index=False)
zip_diag.to_stata(diag_dta, write_index=False)

print("Wrote:", out_dta)
print("Wrote:", out_csv)
print("Wrote:", diag_csv)
print("Wrote:", diag_dta)
print("ZIPs kept:", zip_month["zipnum"].nunique() if not zip_month.empty else 0)
print("Rows:", len(zip_month))

if not zip_diag.empty:
    print("\nZIP diagnostics:")
    print(zip_diag["status"].value_counts(dropna=False))
# %%
