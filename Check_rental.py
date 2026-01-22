#%%
"""
Contract rent (monthly) vs ask rent (listing prices), 2010-01..2022-12.
ZIP column: 'SITUS ZIP CODE' stored as 9 digits (ZIP+4). We convert to ZIP5.
"""
import os, re, glob
import numpy as np
import pandas as pd

# -----------------------------
# SETTINGS
# -----------------------------
# START_YM, END_YM = "2010-01", "2022-12" // data period in our project
START_YM, END_YM = "2015-01", "2020-12" 

# -----------------------------
# Read Data
# -----------------------------

import pandas as pd
from pathlib import Path
from collections import defaultdict

base_dir = Path("/project/cl/data_parquet/MLS_premium2025")

# columns to read
cols = [
    "SITUS STATE",
    "SITUS COUNTY",
    "SITUS ZIP CODE",
    "RENT AMOUNT",
    "ORIGINAL LISTING PRICE",
    "CURRENT LISTING PRICE",
    "LISTING TYPE",
    "LISTING TRANSACTION TYPE CODE DERIVED",
    "INCOME PROPERTY - MONTHLY RENTAL INCOME"
]

dfs = []
year_counts = defaultdict(int)

for year in range(2015, 2021):
    for month in range(1, 13):
        fname = base_dir / f"MLS_{year}-{month:02d}.parquet"
        if not fname.exists():
            continue

        print(f"Reading {fname}")
        df = pd.read_parquet(fname, columns=cols)

        # count number of rows
        year_counts[year] += len(df)      # or df.shape[0]

        dfs.append(df)

# print yearly row counts
print("\nNumber of rows by year:")
for year in sorted(year_counts):
    print(f"{year}: {year_counts[year]:,}")

# combine all data
df_all = pd.concat(dfs, ignore_index=True)

df_all.to_parquet(
    base_dir / "combined_2015_2020.parquet",
    index=False
)

# -----------------------------------------------------
# Rental Listings
# -----------------------------------------------------

# Rental listings only
df_rental = df_all[
    (df_all["LISTING TYPE"] == "For Lease") |
    (df_all["LISTING TRANSACTION TYPE CODE DERIVED"] == "R")
].copy()

# def is_nonmissing_positive(x):
#     return pd.notna(x) and str(x).strip() not in ["", "0", "0.0", "0.00"]

# # Rental indicator
# df_rental = df_all[
#     (df_all["RENT AMOUNT"].apply(is_nonmissing_positive)) |
#     (df_all["INCOME PROPERTY - MONTHLY RENTAL INCOME"].apply(is_nonmissing_positive))
# ].copy()

print("Total listings:", len(df_all))
print("Rental listings:", len(df_rental))

#%%
# -----------------------------------------------------
# LA ZIP code definition
# -----------------------------------------------------

# Convert ZIP9 / messy ZIP to ZIP5 integer
def zip9_to_zip5(s: pd.Series) -> pd.Series:
    z5 = (
        s.astype("string")
         .str.extract(r"^(\d{5})", expand=False)
    )
    return z5.astype("Int64")

df_rental["zip5"] = zip9_to_zip5(df_rental["SITUS ZIP CODE"])

# -----------------------------------------------------
# LA County ZIP definition (broad but accurate)
# -----------------------------------------------------
LA_COUNTY_ZIP_RANGES = [
    (90001, 90089),  # City of LA core
    (90094, 90096),  # Playa Vista etc.
    (90201, 90212),
    (90220, 90292),
    (90301, 90313),
    (90401, 90411),
    (90501, 90510),
    (90701, 90755),
    (90801, 90899),
    (91001, 91099),
    (91101, 91199),
    (91201, 91299),
    (91301, 91399),
    (91401, 91499),
    (91501, 91599),
    (91601, 91699),
    (91701, 91799),
    (91801, 91899),
]

# Build mask programmatically
la_county_mask = False
for lo, hi in LA_COUNTY_ZIP_RANGES:
    la_county_mask |= df_rental["zip5"].between(lo, hi)

df_rental["is_LA_county_zip"] = la_county_mask.fillna(False)

# Subset LA County rentals
df_rental_LA_county = df_rental[
    (df_rental["is_LA_county_zip"]) | (df_rental["SITUS COUNTY"] == "LOS ANGELES")
].copy()

print("Rental listings in LA County ZIPs:", len(df_rental_LA_county))



#%%

# -----------------------------
# Check number of observations
# -----------------------------

# Number of rows by year (All Listings):
# 2015: 5,415,762
# 2016: 5,389,901
# 2017: 5,337,803
# 2018: 5,611,224
# 2019: 5,666,938
# 2020: 5,492,988


#%%
import numpy as np
import pandas as pd

COL_RENT = "RENT AMOUNT"
COL_ORIG = "ORIGINAL LISTING PRICE"
COL_CURR = "CURRENT LISTING PRICE"

# -----------------------------------------------------
# 1. Clean numeric columns
# -----------------------------------------------------
df = df_rental_LA_county.copy()

for c in [COL_RENT, COL_ORIG, COL_CURR]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

df = df.replace([np.inf, -np.inf], np.nan)

# Enforce economically meaningful values
df.loc[df[COL_RENT] <= 0, COL_RENT] = np.nan
df.loc[df[COL_ORIG] <= 0, COL_ORIG] = np.nan
df.loc[df[COL_CURR] <= 0, COL_CURR] = np.nan

# -----------------------------------------------------
# 2. Compute ratios (row-level)
# -----------------------------------------------------
df["rent_over_orig_price"] = df[COL_RENT] / df[COL_ORIG]
df["rent_over_curr_price"] = df[COL_RENT] / df[COL_CURR]

# -----------------------------------------------------
# 3. Report mean and median
# -----------------------------------------------------
summary = pd.DataFrame({
    "variable": [
        "RENT AMOUNT",
        "ORIGINAL LISTING PRICE",
        "CURRENT LISTING PRICE",
        "RENT / ORIGINAL LISTING PRICE",
        "RENT / CURRENT LISTING PRICE",
    ],
    "mean": [
        df[COL_RENT].mean(),
        df[COL_ORIG].mean(),
        df[COL_CURR].mean(),
        df["rent_over_orig_price"].mean(),
        df["rent_over_curr_price"].mean(),
    ],
    "median": [
        df[COL_RENT].median(),
        df[COL_ORIG].median(),
        df[COL_CURR].median(),
        df["rent_over_orig_price"].median(),
        df["rent_over_curr_price"].median(),
    ],
})

print("\n=== LA County Rental Listings: Mean and Median ===")
print(summary.to_string(index=False))

# %%
