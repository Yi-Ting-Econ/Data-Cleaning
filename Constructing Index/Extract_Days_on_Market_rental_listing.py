#%%

import os
import glob
import pandas as pd
import numpy as np

# Define folders
data_folder = "/project/cl/data_csv/MLS_premium2025/"
output_folder = "Edit output file path here"
os.makedirs(output_folder, exist_ok=True)

file_list = []
for year in range(2011, 2022):
    file_list.extend(glob.glob(os.path.join(data_folder, f"MLS_{year}-*.csv")))

# Columns to read
use_cols = [
    'CLIP', 'LISTING DATE', 'OFF MARKET DATE', 'CLOSE DATE',
    'LISTING TRANSACTION TYPE CODE DERIVED',
    'PROPERTY TYPE STD NAME STANDARDIZED',
    'REO INDICATOR', 'SHORT SALE INDICATOR', 'FORECLOSURE INDICATOR',
    'LISTING ADDRESS ZIP CODE',
    'NUMBER OF BEDROOMS', 'TOTAL BATHS',
    'LIVING AREA SQUARE FEET', 'YEAR BUILT',
    'NUMBER OF GARAGE SPACES', 'TOTAL NUMBER OF PARKING SPACES'
]

all_data = []

for file_path in sorted(file_list):
    print(f"Reading {file_path}")
    try:
        df = pd.read_csv(file_path, usecols=use_cols, low_memory=False)
    except Exception as e:
        print(f"Failed: {file_path} → {e}")
        continue

    # Dates
    for col in ['LISTING DATE', 'OFF MARKET DATE', 'CLOSE DATE']:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    # Keep all rows; do NOT drop duplicate CLIP values

    # Filter for rental listings
    df = df[df['PROPERTY TYPE STD NAME STANDARDIZED'] == 'Single Family'].copy()
    df = df[df['LISTING TRANSACTION TYPE CODE DERIVED'] == 'R'].copy()

    for col in ['REO INDICATOR', 'SHORT SALE INDICATOR', 'FORECLOSURE INDICATOR']:
        if col in df.columns:
            df[col] = df[col].fillna('N').astype(str).str.upper().str.strip()
            df = df[df[col] != 'Y'].copy()

    # Need listing date to compute TOM
    df = df[df['LISTING DATE'].notna()].copy()

    # Only drop if BOTH CLOSE DATE and OFF MARKET DATE are missing
    df = df[~(df['CLOSE DATE'].isna() & df['OFF MARKET DATE'].isna())].copy()

    # Define TOM endpoint:
    # use CLOSE DATE first; if missing, use OFF MARKET DATE
    df['end_date_for_tom'] = df['CLOSE DATE'].fillna(df['OFF MARKET DATE'])

    # TOM
    df['TOM_days'] = (df['end_date_for_tom'] - df['LISTING DATE']).dt.days
    df = df[(df['TOM_days'] > 0) & (df['TOM_days'] <= 365)].copy()
    df['log_TOM'] = np.log(df['TOM_days'])

    # Variables
    df['ZIP'] = df['LISTING ADDRESS ZIP CODE'].astype(str).str.zfill(5)
    df['year'] = df['LISTING DATE'].dt.year
    df['month'] = df['LISTING DATE'].dt.month
    df['year_month'] = df['LISTING DATE'].dt.to_period('M').astype(str)

    df['bedrooms'] = pd.to_numeric(df['NUMBER OF BEDROOMS'], errors='coerce')
    df['bathrooms'] = pd.to_numeric(df['TOTAL BATHS'], errors='coerce')
    df['sqft'] = pd.to_numeric(df['LIVING AREA SQUARE FEET'], errors='coerce')
    df['year_built'] = pd.to_numeric(df['YEAR BUILT'], errors='coerce')
    df['garage'] = pd.to_numeric(df['NUMBER OF GARAGE SPACES'], errors='coerce')
    df['parking'] = pd.to_numeric(df['TOTAL NUMBER OF PARKING SPACES'], errors='coerce')

    df = df.dropna(subset=['ZIP', 'bedrooms', 'bathrooms', 'sqft', 'year_built']).copy()

    all_data.append(df)

# Combine all
if len(all_data) == 0:
    raise ValueError("No data loaded successfully.")

combined = pd.concat(all_data, ignore_index=True)

# Clean ZIP column before saving
combined['ZIP'] = combined['ZIP'].astype(str)
combined['ZIP'] = combined['ZIP'].replace('nan', '')
combined.drop(columns=['LISTING ADDRESS ZIP CODE'], inplace=True, errors='ignore')

# Save to Stata
output_path = os.path.join(output_folder, "MLS_rent_panel_extracted.dta")
combined.to_stata(output_path, write_index=False)
print(f"\nSaved full cleaned dataset to: {output_path}")
# %%
