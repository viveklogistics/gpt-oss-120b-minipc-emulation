"""Generate the ILLUSTRATIVE (synthetic) data for tests T2-T5. Fixed seeds -> identical files every run.
No company data is used anywhere. Run:  python gen_data.py   (writes tests/data/*)"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent / "data"
D.mkdir(exist_ok=True)

# ---------------- T2: 78 months of truck dispatches (counts), trend + seasonality + step + noise
def t2():
    rng = np.random.default_rng(20261101)
    n = 78
    months = pd.period_range("2020-01", periods=n, freq="M")
    t = np.arange(n)
    # seasonal index for an illustrative market: strong Mar, weak monsoon Jul-Sep
    season = {1: 1.04, 2: 1.06, 3: 1.14, 4: 1.03, 5: 1.00, 6: 0.93, 7: 0.84, 8: 0.82, 9: 0.88, 10: 0.98, 11: 1.07, 12: 1.21}
    s = np.array([season[m.month] for m in months])
    step = (t >= 48).astype(int)                       # new finishing unit from Jan 2024
    mu = (2400 + 14 * t + 450 * step) * s
    y = rng.poisson(mu * rng.lognormal(0, 0.03, n))
    df = pd.DataFrame({"month": months.astype(str), "trucks": y, "new_unit": step})
    df.to_csv(D / "t2_dispatch.csv", index=False)

# ---------------- T3: 12 invoices to club onto 30 t trucks
def t3():
    inv = [  # id, district, tonnes, product
        ("INV01", "Kestrel", 12, "bag"), ("INV02", "Kestrel", 9, "bag"), ("INV03", "Brindle", 14, "bag"),
        ("INV04", "Brindle", 8, "bulk"), ("INV05", "Larch", 16, "bag"), ("INV06", "Larch", 11, "bag"),
        ("INV07", "Kestrel", 7, "bulk"), ("INV08", "Brindle", 10, "bag"), ("INV09", "Larch", 6, "bulk"),
        ("INV10", "Maple", 13, "bag"), ("INV11", "Maple", 9, "bag"), ("INV12", "Brindle", 5, "bag")]
    pd.DataFrame(inv, columns=["invoice", "district", "tonnes", "product"]).to_csv(D / "t3_invoices.csv", index=False)
    rules = {"truck_capacity_t": 30, "max_trucks": 12, "truck_fixed_cost_rs": 18000, "drop_cost_rs_per_district": 1500,
             "max_districts_per_truck": 2,
             "rules_text": ["Each invoice goes on exactly one truck (no splitting).",
                            "Truck capacity 30 t.",
                            "Bagged ('bag') and bulk ('bulk') product cannot share a truck.",
                            "A truck may serve at most 2 distinct districts.",
                            "INV05 and INV10 must not share a truck (customer delivery windows clash).",
                            "Cost of a used truck = Rs 18,000 fixed + Rs 1,500 per distinct district it serves."],
             "incompatible_pairs": [["INV05", "INV10"]]}
    json.dump(rules, open(D / "t3_rules.json", "w"), indent=1)

# ---------------- T4: small convex QP
def t4():
    qp = {"Q": [[4, 1, 0], [1, 3, 0.5], [0, 0.5, 2]], "c": [-12, -4, 1.5],
          "A": [[1, 1, 1], [1, -1, 0], [0, 1, 2]], "b": [3, 1, 4],
          "form": "minimise 0.5*x'Qx + c'x subject to A x <= b and x >= 0"}
    json.dump(qp, open(D / "t4_qp.json", "w"), indent=1)

# ---------------- T5: 4 plants x 6 districts transport LP
def t5():
    plants = {"P1_Ashford": 42000, "P2_Brindle": 30000, "P3_Calder": 36000, "P4_Dunmore": 28000}
    districts = {"D1_Eastport": 26000, "D2_Fairview": 31000, "D3_Glenrock": 22000, "D4_Harlow": 18000,
                 "D5_Ironvale": 14000, "D6_Juniper": 12000}
    cost = [  # Rs/tonne, illustrative only
        [820, 1150, 1210, 1380, 1290, 1020],
        [960, 760, 1440, 1050, 1170, 1240],
        [1100, 870, 1650, 1300, 840, 1500],
        [1320, 640, 1490, 690, 1420, 1100]]
    json.dump({"plants_capacity_t": plants, "districts_demand_t": districts, "cost_rs_per_t": cost,
               "note": "ILLUSTRATIVE numbers only. Rows = plants (in the order above), columns = districts."},
              open(D / "t5_transport.json", "w"), indent=1)

if __name__ == "__main__":
    t2(); t3(); t4(); t5(); print("wrote", sorted(p.name for p in D.iterdir()))
