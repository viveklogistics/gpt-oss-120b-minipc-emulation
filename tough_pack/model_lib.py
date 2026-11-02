"""Reference-side helpers (never shown to the model): the 3-month network plan built with highspy, an independent
plan validator/costing, the H4 truck-plan validator and the forecast reference. ILLUSTRATIVE SYNTHETIC DATA only."""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import highspy

D = Path(__file__).resolve().parent / "data"

def net():
    P = pd.read_csv(D / "plants.csv"); C = pd.read_csv(D / "intermediate_units.csv")
    L = pd.read_csv(D / "lanes_plant_depot.csv"); CL = pd.read_csv(D / "lanes_intermediate_unit_plant.csv")
    F = json.load(open(D / "freight.json"))
    return P, C, L, CL, F

def solve_plan(dem, rakes=True, cap_override=None, mode="min_cost"):
    """dem: DataFrame depot, month, tonnes. mode='min_cost' or 'max_served' (demand <=, maximise delivered).
    Returns dict(status, cost, sol frames, cap_duals {(plant,month): row dual})."""
    P, C, L, CL, F = net(); cap_override = cap_override or {}
    months = sorted(dem.month.unique()); depots = sorted(dem.depot.unique())
    dm = {(r.depot, r.month): float(r.tonnes) for r in dem.itertuples()}
    km = {(r.plant, r.depot): r.road_km for r in L.itertuples()}; ckm = {(r.intermediate_unit, r.plant): r.rail_km for r in CL.itertuples()}
    h = highspy.Highs(); h.silent(); inf = highspy.kHighsInf
    cf, rk, rkf = F["intermediate_factor_t_per_t_product"], F["rake_size_t"], F["rake_fixed_cost_rs"]
    v = {}
    def var(key, lb=0, ub=inf, cost=0.0, integer=False):
        if mode == "max_served": cost = 0.0
        x = h.addVariable(lb=lb, ub=ub, obj=cost)
        if integer: h.changeColIntegrality(x.index, highspy.HighsVarType.kInteger)
        v[key] = x; return x
    for p in P.itertuples():
        for t in months:
            cap = cap_override.get((p.plant, t), p.finishing_capacity_t_month)
            var(("prod", p.plant, t), 0, cap, p.finishing_var_cost_rs_per_t)
            kc = 0 if pd.isna(p.stage1_intermediate_cost_rs_per_t) else p.stage1_intermediate_cost_rs_per_t
            var(("stage1", p.plant, t), 0, p.stage1_intermediate_capacity_t_month, kc)
            var(("inv", p.plant, t), 0, p.storage_cap_t, p.holding_cost_rs_per_t_month)
            for d in depots: var(("ship", p.plant, d, t), 0, inf, F["product_road_freight_rs_per_t_km"] * km[(p.plant, d)])
            for c in C.itertuples():
                var(("xfer", c.intermediate_unit, p.plant, t), 0, inf, c.intermediate_cost_rs_per_t + F["intermediate_rail_freight_rs_per_t_km"] * ckm[(c.intermediate_unit, p.plant)])
                if rakes: var(("rake", c.intermediate_unit, p.plant, t), 0, 1000, rkf, integer=True)
    if mode == "max_served":
        h.changeObjectiveSense(highspy.ObjSense.kMaximize)
        for p in P.itertuples():
            for d in depots:
                for t in months: h.changeColCost(v[("ship", p.plant, d, t)].index, 1.0)
    rows = {}
    for p in P.itertuples():
        for i, t in enumerate(months):
            prev = p.initial_inventory_t if i == 0 else v[("inv", p.plant, months[i - 1])]
            ships = sum(v[("ship", p.plant, d, t)] for d in depots)
            rows[("bal", p.plant, t)] = h.addConstr(v[("inv", p.plant, t)] - v[("prod", p.plant, t)] + ships == prev) if i == 0 else \
                h.addConstr(v[("inv", p.plant, t)] - prev - v[("prod", p.plant, t)] + ships == 0)
            rows[("clk", p.plant, t)] = h.addConstr(cf * v[("prod", p.plant, t)] - v[("stage1", p.plant, t)]
                                                    - sum(v[("xfer", c, p.plant, t)] for c in C.intermediate_unit) == 0)
            if rakes:
                for c in C.intermediate_unit: h.addConstr(v[("xfer", c, p.plant, t)] - rk * v[("rake", c, p.plant, t)] <= 0)
        h.addConstr(v[("inv", p.plant, months[-1])] >= p.end_safety_stock_t)
    for c in C.itertuples():
        for t in months:
            rows[("cu", c.intermediate_unit, t)] = h.addConstr(sum(v[("xfer", c.intermediate_unit, p, t)] for p in P.plant) <= c.intermediate_capacity_t_month)
    for d in depots:
        for t in months:
            e = sum(v[("ship", p, d, t)] for p in P.plant)
            rows[("dem", d, t)] = h.addConstr(e == dm[(d, t)]) if mode == "min_cost" else h.addConstr(e <= dm[(d, t)])
    h.setOptionValue("mip_rel_gap", 1e-7); h.setOptionValue("time_limit", 600.0)
    h.run()
    st = h.modelStatusToString(h.getModelStatus())
    out = {"status": st}
    if st != "Optimal": return out
    sol = h.getSolution(); x = sol.col_value
    val = lambda k: x[v[k].index]
    out["objective"] = h.getInfo().objective_function_value
    out["mip_gap"] = h.getInfo().mip_gap if rakes else 0.0
    prod = [{"plant": p, "month": t, "product_t": val(("prod", p, t)), "stage1_intermediate_t": val(("stage1", p, t))} for p in P.plant for t in months]
    xf = [{"intermediate_unit": c, "plant": p, "month": t, "tonnes": val(("xfer", c, p, t)),
           "rakes": round(val(("rake", c, p, t))) if rakes else 0} for c in C.intermediate_unit for p in P.plant for t in months]
    sh = [{"plant": p, "depot": d, "month": t, "tonnes": val(("ship", p, d, t))} for p in P.plant for d in depots for t in months
          if val(("ship", p, d, t)) > 1e-6]
    out.update(production=pd.DataFrame(prod), transfers=pd.DataFrame(xf), shipments=pd.DataFrame(sh))
    if not rakes and mode == "min_cost":
        rd = sol.row_dual
        out["cap_col_duals"] = {(p, t): sol.col_dual[v[("prod", p, t)].index] for p in P.plant for t in months}
        out["dem_duals"] = {(d, t): rd[rows[("dem", d, t)].index] for d in depots for t in months}
    return out

def check_plan(prod, xfer, ship, dem, rakes=True, cap_override=None, tol=1.0):
    """Independent re-check + costing of a plan (no solver). Returns (feasible, cost, problems)."""
    P, C, L, CL, F = net(); cap_override = cap_override or {}; probs = []
    cf, rk = F["intermediate_factor_t_per_t_product"], F["rake_size_t"]
    months = sorted(dem.month.astype(str).unique())
    for df in (prod, xfer, ship): df["month"] = df["month"].astype(str)
    km = {(r.plant, r.depot): r.road_km for r in L.itertuples()}; ckm = {(r.intermediate_unit, r.plant): r.rail_km for r in CL.itertuples()}
    cost = 0.0
    g = lambda df, keys, col: df.groupby(keys)[col].sum().to_dict()
    pc, pk = g(prod, ["plant", "month"], "product_t"), g(prod, ["plant", "month"], "stage1_intermediate_t")
    xt = g(xfer, ["intermediate_unit", "plant", "month"], "tonnes")
    xr = g(xfer, ["intermediate_unit", "plant", "month"], "rakes") if "rakes" in xfer else {}
    st = g(ship, ["plant", "depot", "month"], "tonnes")
    if min(list(pc.values()) + list(pk.values()) + list(xt.values()) + list(st.values()) + [0]) < -tol: probs.append("negative quantity")
    unknown = {k for k in st if k[:2] not in km}
    if unknown: probs.append(f"unknown lanes {list(unknown)[:3]}")
    for p in P.itertuples():
        inv = p.initial_inventory_t
        for t in months:
            cap = cap_override.get((p.plant, t), p.finishing_capacity_t_month)
            q = pc.get((p.plant, t), 0.0); k = pk.get((p.plant, t), 0.0)
            if q > cap + tol: probs.append(f"{p.plant} {t} finishing {q:.0f} > cap {cap}")
            if k > p.stage1_intermediate_capacity_t_month + tol: probs.append(f"{p.plant} {t} stage1 {k:.0f} > {p.stage1_intermediate_capacity_t_month}")
            tr = sum(xt.get((c, p.plant, t), 0.0) for c in C.intermediate_unit)
            if abs(cf * q - k - tr) > max(tol, 1e-5 * q): probs.append(f"{p.plant} {t} intermediate balance off by {cf*q-k-tr:.1f}")
            out = sum(vv for kk, vv in st.items() if kk[0] == p.plant and kk[2] == t)
            inv = inv + q - out
            if inv < -tol or inv > p.storage_cap_t + tol: probs.append(f"{p.plant} {t} inventory {inv:.0f} outside [0,{p.storage_cap_t}]")
            kc = 0 if pd.isna(p.stage1_intermediate_cost_rs_per_t) else p.stage1_intermediate_cost_rs_per_t
            cost += q * p.finishing_var_cost_rs_per_t + k * kc + max(inv, 0) * p.holding_cost_rs_per_t_month
        if inv < p.end_safety_stock_t - tol: probs.append(f"{p.plant} end inventory {inv:.0f} < safety {p.end_safety_stock_t}")
    for c in C.itertuples():
        for t in months:
            tot = sum(xt.get((c.intermediate_unit, p, t), 0.0) for p in P.plant)
            if tot > c.intermediate_capacity_t_month + tol: probs.append(f"{c.intermediate_unit} {t} {tot:.0f} > cap")
    for (c, p, t), q in xt.items():
        cost += q * (C.set_index("intermediate_unit").intermediate_cost_rs_per_t[c] + F["intermediate_rail_freight_rs_per_t_km"] * ckm[(c, p)])
        if rakes:
            r = xr.get((c, p, t), 0)
            if r is None or (isinstance(r, float) and math.isnan(r)) or abs(r - round(r)) > 1e-6: probs.append(f"non-integer rakes {c} {p} {t}")
            r = round(r or 0)
            if q > rk * r + tol: probs.append(f"{c}->{p} {t}: {q:.0f} t needs more than {r} rakes")
            cost += r * F["rake_fixed_cost_rs"]
    for (p, d, t), q in st.items():
        if (p, d) in km: cost += q * F["product_road_freight_rs_per_t_km"] * km[(p, d)]
    for r in dem.itertuples():
        got = sum(vv for kk, vv in st.items() if kk[1] == r.depot and kk[2] == str(r.month))
        if abs(got - r.tonnes) > tol: probs.append(f"{r.depot} {r.month} delivered {got:.1f} vs demand {r.tonnes}")
    return len(probs) == 0, cost, probs

# ------------------------------------------------------------------ H4 trucks
def h4_check(plan):
    """plan: DataFrame truck_id, slot, invoice_id. Returns (feasible, cost, n_trucks, problems)."""
    inv = pd.read_csv(D / "h4_invoices.csv").set_index("invoice_id"); R = json.load(open(D / "h4_rules.json"))
    probs = []; plan = plan.copy(); plan["invoice_id"] = plan.invoice_id.astype(str).str.strip().str.upper()
    cnt = plan.invoice_id.value_counts()
    if (cnt > 1).any(): probs.append(f"invoices on >1 truck: {list(cnt[cnt > 1].index[:5])}")
    missing = set(inv.index) - set(plan.invoice_id); extra = set(plan.invoice_id) - set(inv.index)
    if missing: probs.append(f"{len(missing)} invoices not loaded e.g. {sorted(missing)[:3]}")
    if extra: probs.append(f"unknown invoices {sorted(extra)[:3]}")
    plan = plan[plan.invoice_id.isin(inv.index)]; cost = 0.0
    for tid, g in plan.groupby("truck_id"):
        rows = inv.loc[g.invoice_id]; slots = g.slot.unique()
        if len(slots) != 1: probs.append(f"truck {tid} has several slots"); continue
        s = int(slots[0])
        if rows.route.nunique() > 1: probs.append(f"truck {tid} mixes routes")
        if rows["product"].nunique() > 1: probs.append(f"truck {tid} mixes bag and bulk")
        if rows.tonnes.sum() > R["truck_capacity_t"]: probs.append(f"truck {tid} overloaded {rows.tonnes.sum()} t")
        if ((rows.earliest_slot > s) | (rows.latest_slot < s)).any(): probs.append(f"truck {tid} slot {s} outside a window")
        nd = rows.district.nunique()
        if nd > R["max_districts_per_truck"]: probs.append(f"truck {tid} serves {nd} districts")
        cost += R["route_fixed_cost_rs_per_truck"][rows.route.iloc[0]] + R["extra_district_cost_rs"] * (nd - 1)
    return len(probs) == 0, cost, plan.truck_id.nunique(), probs

# ------------------------------------------------------------------ forecasting helpers
def design(months_str):
    cal = pd.read_csv(D / "calendar.csv")
    allm = list(pd.period_range("2023-11", periods=39, freq="M").astype(str))
    t = np.array([allm.index(m) for m in months_str]); mo = np.array([int(m[5:7]) for m in months_str])
    fest = pd.Series(0, index=allm); fest.update(cal.set_index("month").festival)
    post = pd.Series(0, index=allm); post.update(cal.set_index("month").post_festival)
    # 2026-12 is the post-festival month of 2026-11: the calendar file lists only history, so derive it
    f = np.array([fest.get(m, 0) for m in months_str]); pf = np.array([post.get(m, 0) for m in months_str])
    X = np.column_stack([np.ones(len(t)), t] + [(mo == k).astype(float) for k in range(2, 13)] + [f, pf])
    return X
