"""ILLUSTRATIVE SYNTHETIC DATA for the tough pack (H1-H9). A made-up supply chain: no real company data,
no real plant names, no real locations. Fixed seed -> identical files every run.  python tough/gen_data.py
Writes tough/data/* (given to the model) and tough/data/hidden/* (truth, never copied into a test folder)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 20261102
D = Path(__file__).resolve().parent / "data"; H = D / "hidden"
D.mkdir(exist_ok=True); H.mkdir(exist_ok=True)
NOTE = "ILLUSTRATIVE SYNTHETIC DATA - made-up network, not real company data"
CF = 0.72                      # t intermediate per t product

def main():
    rng = np.random.default_rng(SEED)
    # ------------------------------------------------ network on a made-up 1000 x 800 km map
    plants = pd.DataFrame({
        "plant": ["P1_Kestrel", "P2_Heron", "P3_Ibis", "P4_Osprey", "P5_Plover", "P6_Wren"],
        "x_km": [150, 480, 820, 300, 650, 900], "y_km": [200, 120, 260, 620, 520, 700],
        "finishing_capacity_t_month": [165000, 145000, 125000, 140000, 118000, 127000],
        "finishing_var_cost_rs_per_t": [610, 560, 640, 590, 700, 655],
        "stage1_intermediate_capacity_t_month": [95000, 90000, 70000, 85000, 0, 0],
        "stage1_intermediate_cost_rs_per_t": [1850, 1790, 1960, 1880, None, None],
        "storage_cap_t": 45000, "initial_inventory_t": [16000, 14000, 12000, 15000, 9000, 11000],
        "end_safety_stock_t": 10000, "holding_cost_rs_per_t_month": 45})
    cus = pd.DataFrame({"intermediate_unit": ["CU1_Basalt", "CU2_Granite"], "x_km": [560, 760], "y_km": [330, 560],
                        "intermediate_capacity_t_month": [85000, 75000], "intermediate_cost_rs_per_t": [1680, 1720]})
    depots = pd.DataFrame({"depot": [f"DP{i:02d}" for i in range(1, 41)],
                           "x_km": rng.uniform(40, 980, 40).round(0), "y_km": rng.uniform(40, 780, 40).round(0)})
    n = 300
    dx, dy = rng.uniform(20, 990, n).round(0), rng.uniform(20, 790, n).round(0)
    dist = np.hypot(dx[:, None] - depots.x_km.values, dy[:, None] - depots.y_km.values)
    dep_idx = dist.argmin(1)
    # depot -> home plant (nearest) defines the forecasting hierarchy district -> plant -> total
    pd_dist = np.hypot(depots.x_km.values[:, None] - plants.x_km.values, depots.y_km.values[:, None] - plants.y_km.values)
    home = plants.plant.values[pd_dist.argmin(1)]
    districts = pd.DataFrame({"district": [f"DS{i:03d}" for i in range(1, n + 1)], "x_km": dx, "y_km": dy,
                              "depot": depots.depot.values[dep_idx],
                              "depot_to_district_km": (dist[np.arange(n), dep_idx] * 1.3 + 8).round(0)})
    districts["home_plant"] = home[dep_idx]
    depots["home_plant"] = home
    lanes = [{"plant": p.plant, "depot": d.depot, "road_km": round(float(np.hypot(p.x_km - d.x_km, p.y_km - d.y_km)) * 1.3 + 15)}
             for p in plants.itertuples() for d in depots.itertuples()]
    clanes = [{"intermediate_unit": c.intermediate_unit, "plant": p.plant, "rail_km": round(float(np.hypot(p.x_km - c.x_km, p.y_km - c.y_km)) * 1.2 + 40)}
              for c in cus.itertuples() for p in plants.itertuples()]
    freight = {"note": NOTE, "product_road_freight_rs_per_t_km": 2.6, "intermediate_rail_freight_rs_per_t_km": 1.35,
               "rake_size_t": 3800, "rake_fixed_cost_rs": 250000, "intermediate_factor_t_per_t_product": CF,
               "secondary_truck_capacity_t": 30, "secondary_truck_fixed_rs": 1800, "secondary_truck_rs_per_km": 38}

    # ------------------------------------------------ 39 months of district demand (36 given + 3 hidden actuals)
    months = pd.period_range("2023-11", periods=39, freq="M")
    season = {1: 1.10, 2: 1.12, 3: 1.16, 4: 1.06, 5: 1.02, 6: 0.94, 7: 0.80, 8: 0.78, 9: 0.84, 10: 0.97, 11: 1.03, 12: 1.08}
    fest_months = {"2023-11", "2024-10", "2025-10", "2026-11"}          # illustrative festival month (Diwali-like)
    fest = np.array([str(m) in fest_months for m in months]).astype(int)
    post = np.r_[0, fest[:-1]]
    cal = pd.DataFrame({"month": months.astype(str), "festival": fest, "post_festival": post})
    base = rng.lognormal(np.log(1450), 0.45, n)
    growth = rng.uniform(0.02, 0.10, n) / 12
    t = np.arange(39)
    s = np.array([season[m.month] for m in months])
    mult = s * np.where(fest == 1, 0.86, 1.0) * np.where(post == 1, 1.07, 1.0)
    noise = rng.lognormal(0, 0.07, (n, 39))
    dem = base[:, None] * np.exp(growth[:, None] * t) * mult * noise           # tonnes, district x month
    dem = dem.round(1)
    panel = pd.DataFrame(dem, columns=months.astype(str)); panel.insert(0, "district", districts.district)
    long = panel.melt(id_vars="district", var_name="month", value_name="tonnes")
    hist = long[long.month <= "2026-10"].reset_index(drop=True)
    fut = long[long.month > "2026-10"].reset_index(drop=True)

    # ------------------------------------------------ H1 raw invoices with planted problems
    rows = []; k = 0
    for r in hist.itertuples():
        m = int(rng.integers(1, 5)); w = rng.dirichlet([3] * m)
        q = np.round(r.tonnes * w, 1); q[-1] = round(r.tonnes - q[:-1].sum(), 1)
        for qq in q:
            k += 1
            day = int(rng.integers(1, 28))
            rows.append({"invoice_id": f"INV{k:06d}", "invoice_date": f"{r.month}-{day:02d}", "district": r.district,
                         "qty": float(qq), "uom": "MT", "_dm": (r.district, r.month)})
    inv = pd.DataFrame(rows)
    inv = inv[inv.qty > 0.5].reset_index(drop=True)
    # (a) missing district-months: remove every invoice of 23 district-months (not the first/last month)
    dms = sorted(set(inv._dm)); mid = [dm for dm in dms if dm[1] not in ("2023-11", "2026-10")]
    miss_idx = rng.choice(len(mid), 23, replace=False); missing = {mid[i] for i in miss_idx}
    inv = inv[~inv._dm.isin(missing)].reset_index(drop=True)
    # (b) one big outlier: qty keyed 100x too large
    out_i = int(rng.integers(0, len(inv)))
    while inv.loc[out_i, "qty"] < 300: out_i += 1
    inv.loc[out_i, "qty"] = round(inv.loc[out_i, "qty"] * 100, 1)
    outlier_id = inv.loc[out_i, "invoice_id"]
    # (c) 58 rows recorded in 50 kg bags instead of tonnes
    cand = [i for i in range(len(inv)) if i != out_i]
    bag_i = rng.choice(cand, 58, replace=False)
    labels = ["BAG", "Bags", "bags(50kg)"]
    for j, i in enumerate(bag_i):
        inv.loc[i, "qty"] = round(inv.loc[i, "qty"] * 20); inv.loc[i, "uom"] = labels[j % 3]
    # (d) 37 exact duplicate rows (re-keyed invoices), never of a bag row or the outlier
    cand = [i for i in range(len(inv)) if i != out_i and i not in set(bag_i)]
    dup_i = rng.choice(cand, 37, replace=False)
    raw = pd.concat([inv, inv.loc[dup_i]]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    # cleaned truth total: dedupe, bags->t, drop outlier, before imputation
    clean = inv.copy(); isbag = clean.uom != "MT"
    clean.loc[isbag, "qty"] = clean.loc[isbag, "qty"] * 0.05
    clean_total = float(clean.loc[clean.invoice_id != outlier_id, "qty"].sum())
    raw.drop(columns="_dm").to_csv(D / "h1_invoices_raw.csv", index=False)

    # ------------------------------------------------ write shared files
    plants.to_csv(D / "plants.csv", index=False); cus.to_csv(D / "intermediate_units.csv", index=False)
    depots.to_csv(D / "depots.csv", index=False); districts.to_csv(D / "districts.csv", index=False)
    pd.DataFrame(lanes).to_csv(D / "lanes_plant_depot.csv", index=False)
    pd.DataFrame(clanes).to_csv(D / "lanes_intermediate_unit_plant.csv", index=False)
    json.dump(freight, open(D / "freight.json", "w"), indent=1)
    cal.to_csv(D / "calendar.csv", index=False)
    hist.to_csv(D / "demand_clean.csv", index=False)            # complete, clean 36-month panel for H2/H7
    fut.to_csv(H / "actuals_future.csv", index=False)           # hidden: the 3 months that are forecast
    # H3 depot demand = the hidden actual district demand of the 3 months, by depot
    fd = fut.merge(districts[["district", "depot"]]).groupby(["depot", "month"], as_index=False).tonnes.sum()
    fd["tonnes"] = fd.tonnes.round(0)
    fd.to_csv(D / "h3_depot_demand.csv", index=False)
    # H5 trap: an illustrative surge (+15%), finishing still enough each month, intermediate is not
    h5 = fd.copy(); h5["tonnes"] = (h5.tonnes * 1.15).round(0); h5.to_csv(D / "h5_depot_demand.csv", index=False)
    json.dump({"note": NOTE, "seed": SEED, "h1": {"n_duplicate_rows": 37, "n_bag_rows": 58, "n_outlier_rows": 1,
               "outlier_invoice_id": outlier_id, "n_missing_district_months": 23,
               "missing": sorted(map(list, missing)), "clean_total_tonnes": round(clean_total, 1),
               "raw_rows": len(raw)}}, open(H / "h1_truth.json", "w"), indent=1)

    # ------------------------------------------------ H4: ~200 invoices to club onto trucks
    r4 = np.random.default_rng(SEED + 4)
    routes = [f"R{i:02d}" for i in range(1, 11)]
    route_fixed = dict(zip(routes, [9000, 11500, 12500, 14000, 15500, 16500, 18000, 19500, 21000, 22500]))
    rows = []
    for i in range(200):
        ro = routes[i % 10]
        dset = [f"{ro}-D{j}" for j in range(1, 6)]
        e = int(r4.integers(1, 4)); l = int(r4.integers(e, 4))
        rows.append({"invoice_id": f"OB{i + 1:03d}", "route": ro, "district": dset[int(r4.integers(0, 5))],
                     "tonnes": int(r4.integers(3, 19)), "product": "bag" if r4.random() < 0.6 else "bulk",
                     "earliest_slot": e, "latest_slot": l})
    pd.DataFrame(rows).sample(frac=1, random_state=4).to_csv(D / "h4_invoices.csv", index=False)
    json.dump({"note": NOTE, "truck_capacity_t": 30, "max_districts_per_truck": 3, "slots": [1, 2, 3],
               "route_fixed_cost_rs_per_truck": route_fixed, "extra_district_cost_rs": 1200,
               "rules": ["each invoice on exactly one truck, no splitting", "a truck serves one route only",
                         "bag and bulk never share a truck", "a truck leaves in ONE slot, which must lie inside "
                         "[earliest_slot, latest_slot] of every invoice on it", "load <= truck_capacity_t",
                         "distinct districts on a truck <= max_districts_per_truck",
                         "truck cost = route fixed cost + extra_district_cost_rs * (distinct districts - 1)"]},
              open(D / "h4_rules.json", "w"), indent=1)
    print("data written to", D)

if __name__ == "__main__":
    main()
