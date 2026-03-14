# Constructing the Repeated-Listing Time-on-Market (TOM) Index

This document describes the procedure used to construct a **Repeated-Listing Time-on-Market (TOM) Index** using CoreLogic MLS listing data.

The approach follows the logic of the **Case–Shiller repeated-sales index**, adapted to measure **time on market instead of prices**.

The index can be constructed separately for:

- **Time to Sell** (sales listings)
- **Time to Lease** (rental listings)

---

# Overview

The repeated-listing index isolates **market-wide changes in time on market** by comparing the same property across multiple listings.

For example, we observe in the data:

```
Property A
│
├── Listing 1: 2013   TOM = 40 days
│
├── Listing 2: 2016   TOM = 55 days
│
└── Listing 3: 2019   TOM = 30 days
```

Construct pairs:

```
(2013 → 2016)
(2016 → 2019)
```

Each pair contributes to estimating changes in the TOM index.


The goal is to control for **time-invariant property characteristics**, similar to a repeated-sales house price index.

---

# Step 1. Extract MLS Listing Data and Construct Time on Market

Each observation corresponds to a **listing** from the CoreLogic MLS dataset.

Required variables:

| Variable | Description |
|---|---|
| `clip` | Property identifier |
| `listing date` | Date when the property was listed |
| `off market date` | Date when the listing was removed from the market |
| `close date` | Transaction closing date (if applicable) |

Transaction types:

Sales listings: LISTING TRANSACTION TYPE CODE DERIVED == "S"

Rental listings: LISTING TRANSACTION TYPE CODE DERIVED == "R"


### Definition of Time on Market

Time on market is defined as: TOM = CLOSE DATE - LISTING DATE

If the closing date is missing: TOM = OFF MARKET DATE - LISTING DATE


A listing is **only dropped if both `OFF MARKET DATE` and `CLOSE DATE` are missing**.

Note:

> It is normal for many listings to have missing closing dates because not all listings lead to a successful transaction.

---

# Step 2. Construct Repeat-Listing Pairs

Sort listings by: 
clip
listing date


For properties that appear **multiple times between 2011–2022**, form **pairs of consecutive listings**.

Example:

| clip | listing date | TOM |
|---|---|---|
| A | 2013 | 40 |
| A | 2016 | 55 |
| A | 2019 | 30 |

Construct pairs:
(2013, 2016)
(2016, 2019)


Note that:

Only **consecutive listings** are paired.

Do **not** create pairs like `(2013, 2019)`.

---

# Step 3. Create Time Dummy Variables

For each pair \(i\):
D_it = 1 if t = month of later listing
D_it = -1 if t = month of earlier listing
D_it = 0 otherwise


These dummy variables encode **changes in time on market across months**.

Illustration:
Month Dummy
2013m5 -1
2014m* 0
2015m* 0
2016m3 +1


---

# Step 4. Estimate the Repeated-Listing Regression

For each listing pair \(i\):

ΔTOMᵢ = Σₜ Dᵢₜ γₜ + εᵢ

Where:

| Symbol | Meaning |
|---|---|
| ΔTOMᵢ | Difference in time on market between two listings |
| Dᵢₜ | Time dummy variables |
| γₜ | Monthly index coefficients |
| εᵢ | Residual |

The estimated coefficients **γₜ form the TOM index**.

---

# Step 5 (Optional). Case–Shiller Variance Weighting

Following the Case–Shiller methodology:

1. Estimate a **variance model** for regression residuals.
2. Variance increases with the **gap between listings**.
3. Assign **weights inversely proportional to the estimated variance**.

Intuition:

Short listing gap → more reliable signal → higher weight
Long listing gap → more noise → lower weight


---

# Step 6. Normalize and Interpret the Index

Normalize the index to a base period.

Example:
Base period: 2015m1
Index(2015m1) = 100


Interpretation:

| Index | Meaning |
|---|---|
| 110 | Time on market is 10% longer than 2015m1 |
| 90 | Time on market is 10% shorter than 2015m1 |

This interpretation is analogous to the **Consumer Price Index (CPI)**.

---

# Final Output

The final output is a **monthly Time-on-Market index**.

Separate indices can be constructed for:

- **Time to Sell (sales listings)**
- **Time to Lease (rental listings)**

---

# Implementation Notes

Results may vary depending on implementation details such as:

- trimming extreme TOM values
- outlier removal
- minimum number of pairs required within a geographic unit (e.g., ZIP code)

Independent implementations are encouraged to **replicate the procedure using the guidelines rather than the code**, in order to cross-check the robustness of results.




