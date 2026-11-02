"""Compute every reference answer for H1-H9 with solvers (never the model). Writes data/hidden/reference.json.
ILLUSTRATIVE SYNTHETIC DATA only.   python tough/reference.py"""
import json, math, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import highspy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_lib import D, net, solve_plan, check_plan, h4_check, design

H = D / "hidden"; FUT = ["2026-11", "2026-12", "2027-01"]

def mape(a, f): a, f = np.asarray(a, float), np.asarray(f, float); return float(np.mean(np.abs(a - f) / a) * 100)

def ols_log_forecast(hist, months_fit, months_out):
    """Per-district OLS of log(tonnes) on const, t, 11 month dummies, festival, post_festival; exp(prediction)."""
    Xf, Xo = design(months_fit), design(months_out); out = {}; resvar = {}
    piv = hist.pivot(index="district", columns="month", values="tonnes")[months_fit]
    for d, y in piv.iterrows():
        b, *_ = np.linalg.lstsq(Xf, np.log(y.values), rcond=None)
        out[d] = np.exp(Xo @ b); r = y.values - np.exp(Xf @ b); resvar[d] = float(np.mean(r ** 2))
    return out, resvar

def agg_forecast(series, months_fit, months_out):
    Xf, Xo = design(months_fit), design(months_out)
    b, *_ = np.linalg.lstsq(Xf, np.log(series.values), rcond=None)
    return np.exp(Xo @ b), float(np.mean((series.values - np.exp(Xf @ b)) ** 2))

def reconcile(dist_fc, dist_var, hier, hist, months_fit, months_out):
    """WLS (variance scaling) reconciliation total -> plant -> district."""
    dists = sorted(dist_fc); plants = sorted(hier.unique())
    S = np.vstack([np.ones(len(dists))] + [(hier[dists] == p).values.astype(float) for p in plants] + [np.eye(len(dists))])
    piv = hist.pivot(index="district", columns="month", values="tonnes")[months_fit]
    base, var = [], []
    tf, tv = agg_forecast(piv.sum(), months_fit, months_out); base.append(tf); var.append(tv)
    for p in plants:
        f, vv = agg_forecast(piv.loc[hier[hier == p].index].sum(), months_fit, months_out); base.append(f); var.append(vv)
    for d in dists: base.append(dist_fc[d]); var.append(dist_var[d])
    Y = np.vstack(base); Wi = np.diag(1 / np.array(var))
    G = np.linalg.solve(S.T @ Wi @ S, S.T @ Wi)
    rec = S @ (G @ Y)
    return rec, ["TOTAL"] + plants + dists

def main():
    t0 = time.time(); ref = json.load(open(H / "h1_truth.json")); P, C, L, CL, F = net()
    dist = pd.read_csv(D / "districts.csv").set_index("district"); hier = dist.home_plant
    hist = pd.read_csv(D / "demand_clean.csv"); act = pd.read_csv(H / "actuals_future.csv")
    months = sorted(hist.month.unique())
    # ---------------- H1 sanity: recompute the counts from the raw file the way a careful analyst would
    raw = pd.read_csv(D / "h1_invoices_raw.csv")
    dd = raw.drop_duplicates(); bag = ~dd.uom.str.upper().eq("MT"); dd = dd.copy(); dd.loc[bag, "qty"] *= 0.05
    med = dd.groupby("district").qty.transform("median"); outl = dd.qty > 20 * med
    present = set(zip(dd.district, dd.invoice_date.str[:7]))
    nmiss = sum((d, m) not in present for d in dist.index for m in months)
    chk = {"n_duplicate_rows": len(raw) - len(dd), "n_bag_rows": int(bag.sum()), "n_outlier_rows": int(outl.sum()),
           "n_missing_district_months": nmiss, "clean_total_tonnes": round(float(dd.loc[~outl, "qty"].sum()), 1)}
    for k, v in chk.items(): assert abs(v - ref["h1"][k]) < 0.5, (k, v, ref["h1"][k])
    ref["h1"]["independent_recount"] = chk
    # ---------------- H2 forecast + WLS reconciliation; holdout = last 3 history months; future = hidden actuals
    fc, rv = ols_log_forecast(hist, months, FUT)
    rec, ids = reconcile(fc, rv, hier, hist, months, FUT)
    nd = len(fc); recd = rec[-nd:]
    a = act.pivot(index="district", columns="month", values="tonnes").loc[sorted(fc)][FUT].values
    fc_h, rv_h = ols_log_forecast(hist, months[:-3], months[-3:])
    rec_h, _ = reconcile(fc_h, rv_h, hier, hist, months[:-3], months[-3:])
    ah = hist.pivot(index="district", columns="month", values="tonnes").loc[sorted(fc)][months[-3:]].values
    # comparison models so the pass band is calibrated, not guessed
    piv = hist.pivot(index="district", columns="month", values="tonnes").loc[sorted(fc)]
    snaive = piv[["2025-11", "2025-12", "2026-01"]].values * (piv[months[-12:]].sum(axis=1) / piv[months[-24:-12]].sum(axis=1)).values[:, None]
    ref["h2"] = {"future_months": FUT, "ref_model": "per-district OLS on log(t): const,t,11 month dummies,festival,post_festival; WLS(variance) reconciliation",
                 "ref_district_mape_future": round(mape(a, recd), 3), "ref_district_mape_holdout": round(mape(ah, rec_h[-nd:]), 3),
                 "ref_unreconciled_mape_future": round(mape(a, np.vstack([fc[d] for d in sorted(fc)])), 3),
                 "seasonal_naive_growth_mape_future": round(mape(a, snaive), 3),
                 "ref_total_forecast": [round(float(x), 1) for x in rec[0]],
                 "actual_total": [round(float(x), 1) for x in a.sum(0)]}
    # ---------------- H3 MILP (rakes) on h3_depot_demand
    d3 = pd.read_csv(D / "h3_depot_demand.csv"); s3 = solve_plan(d3, rakes=True)
    ok, c3, pr = check_plan(s3["production"], s3["transfers"], s3["shipments"], d3, rakes=True)
    assert ok, pr[:5]
    ref["h3"] = {"status": s3["status"], "optimal_cost_rs": round(s3["objective"], 0), "recheck_cost_rs": round(c3, 0),
                 "mip_gap": s3["mip_gap"], "rakes_total": int(s3["transfers"].rakes.sum())}
    # ---------------- H5 trap
    d5 = pd.read_csv(D / "h5_depot_demand.csv"); s5 = solve_plan(d5, rakes=True)
    s5lp = solve_plan(d5, rakes=False)
    mx = solve_plan(d5, rakes=False, mode="max_served")
    need = d5.tonnes.sum() + P.end_safety_stock_t.sum() - P.initial_inventory_t.sum()
    clk = 3 * (P.stage1_intermediate_capacity_t_month.sum() + C.intermediate_capacity_t_month.sum())
    ref["h5"] = {"milp_status": s5["status"], "lp_status": s5lp["status"], "demand_total_t": float(d5.tonnes.sum()),
                 "max_deliverable_t": round(mx["objective"], 0), "shortfall_t": round(d5.tonnes.sum() - mx["objective"], 0),
                 "product_needed_t": float(need), "product_supported_by_intermediate_t": round(clk / F["intermediate_factor_t_per_t_product"], 0),
                 "finishing_capacity_3m_t": float(3 * P.finishing_capacity_t_month.sum()),
                 "monthly_demand_vs_finishing": {m: [float(d5[d5.month == m].tonnes.sum()), float(P.finishing_capacity_t_month.sum())] for m in FUT},
                 "binding": "intermediate supply (stage-1 lines + intermediate units) over the 3 months"}
    # ---------------- H6 what-if: LP version (continuous transfers, no rake cost), outage day 16 of month 2
    b6 = solve_plan(d3, rakes=False)
    duals = {k: -v for k, v in b6["cap_col_duals"].items()}          # saving per extra tonne (>= 0)
    m2 = FUT[1]; cand = sorted(((duals[(p, m2)], p) for p in P.plant), reverse=True)
    plant = cand[0][1]; capp = float(P.set_index("plant").finishing_capacity_t_month[plant]); lost = capp * 15 / 30
    o6 = solve_plan(d3, rakes=False, cap_override={(plant, m2): capp - lost})
    fd = {}
    for dlt in (+1.0, -1.0):
        s = solve_plan(d3, rakes=False, cap_override={(plant, m2): capp + dlt}); fd[dlt] = (b6["objective"] - s["objective"]) / dlt
    o_duals = {p: -o6["cap_col_duals"][(p, m2)] for p in P.plant}
    ref["h6"] = {"outage_plant": plant, "outage_month": m2, "capacity_t": capp, "lost_capacity_t": lost,
                 "base_cost_rs": round(b6["objective"], 0), "outage_cost_rs": round(o6["objective"], 0),
                 "delta_rs": round(o6["objective"] - b6["objective"], 0),
                 "base_shadow_saving_rs_per_t": round(duals[(plant, m2)], 3),
                 "finite_diff_plus1": round(fd[1.0], 3), "finite_diff_minus1": round(fd[-1.0], 3),
                 "dual_x_lost_rs": round(duals[(plant, m2)] * lost, 0),
                 "all_base_month2_shadow": {p: round(duals[(p, m2)], 3) for p in P.plant},
                 "outage_month2_shadow": {p: round(v, 3) for p, v in o_duals.items()}}
    # ---------------- H9 contradiction uses the same LP base; the contradicting capacity is stated in the prompt
    p9 = "P5_Plover"; file_cap = int(P.set_index("plant").finishing_capacity_t_month[p9])
    s9 = solve_plan(d3, rakes=False, cap_override={(p9, m): 150000 for m in FUT})
    ref["h9"] = {"plant": p9, "file_capacity_t": file_cap, "prompt_capacity_t": 150000,
                 "cost_with_file_capacity_rs": ref["h6"]["base_cost_rs"], "cost_with_prompt_capacity_rs": round(s9["objective"], 0)}
    # ---------------- H4 trucks: exact optimum by (route, product) decomposition, each part a MILP proven by HiGHS
    inv = pd.read_csv(D / "h4_invoices.csv"); R = json.load(open(D / "h4_rules.json"))
    plan, tot, gaps = [], 0.0, []
    for (ro, prd), g in inv.groupby(["route", "product"]):
        g = g.reset_index(drop=True); n = len(g); K = n; dists = sorted(g.district.unique())
        h = highspy.Highs(); h.silent(); B = highspy.HighsVarType.kInteger
        def b(cost=0.0):
            x = h.addVariable(lb=0, ub=1, obj=cost); h.changeColIntegrality(x.index, B); return x
        y = [b(R["route_fixed_cost_rs_per_truck"][ro] - R["extra_district_cost_rs"]) for _ in range(K)]
        x = [[b() for _ in range(K)] for _ in range(n)]
        z = [[b() for _ in range(3)] for _ in range(K)]
        w = [[b(R["extra_district_cost_rs"]) for _ in dists] for _ in range(K)]
        for i in range(n): h.addConstr(sum(x[i]) == 1)
        for k in range(K):
            h.addConstr(sum(g.tonnes[i] * x[i][k] for i in range(n)) <= R["truck_capacity_t"] * y[k])
            h.addConstr(sum(z[k]) == y[k]); h.addConstr(sum(w[k]) <= R["max_districts_per_truck"])
            for i in range(n):
                h.addConstr(x[i][k] <= sum(z[k][s - 1] for s in range(g.earliest_slot[i], g.latest_slot[i] + 1)))
                h.addConstr(x[i][k] <= w[k][dists.index(g.district[i])])
            if k: h.addConstr(y[k] <= y[k - 1])
        h.setOptionValue("mip_rel_gap", 0.0); h.setOptionValue("time_limit", 300.0); h.run()
        assert h.modelStatusToString(h.getModelStatus()) == "Optimal", (ro, prd)
        xv = h.getSolution().col_value; tot += h.getInfo().objective_function_value; gaps.append(h.getInfo().mip_gap)
        for k in range(K):
            if xv[y[k].index] > 0.5:
                s = 1 + int(np.argmax([xv[z[k][j].index] for j in range(3)]))
                for i in range(n):
                    if xv[x[i][k].index] > 0.5: plan.append({"truck_id": f"{ro}-{prd}-{k + 1}", "slot": s, "invoice_id": g.invoice_id[i]})
    plan = pd.DataFrame(plan); ok, c4, nt, pr = h4_check(plan); assert ok, pr
    plan.to_csv(H / "h4_reference_plan.csv", index=False)
    lb = sum(math.ceil(gg.tonnes.sum() / 30) * R["route_fixed_cost_rs_per_truck"][ro] for (ro, _), gg in inv.groupby(["route", "product"]))
    ref["h4"] = {"optimal_cost_rs": round(c4, 0), "trucks": nt, "max_part_gap": max(gaps), "proven_by": "HiGHS per (route,product) part, gap 0",
                 "simple_capacity_lower_bound_rs": lb}
    # ---------------- H7 chain: specified forecast -> depot demand -> H3 MILP -> secondary trucks
    dep = dist.depot
    fdf = pd.DataFrame([{"district": d, "month": m, "forecast_t": fc[d][j]} for d in fc for j, m in enumerate(FUT)])
    dd7 = fdf.assign(depot=fdf.district.map(dep)).groupby(["depot", "month"], as_index=False).forecast_t.sum()
    dd7 = dd7.rename(columns={"forecast_t": "tonnes"}); dd7["tonnes"] = dd7.tonnes.round(0)
    s7 = solve_plan(dd7, rakes=True); ok, c7, pr = check_plan(s7["production"], s7["transfers"], s7["shipments"], dd7); assert ok, pr[:3]
    fdf["trucks"] = np.ceil(fdf.forecast_t / F["secondary_truck_capacity_t"]).astype(int)
    fdf["sec_cost"] = fdf.trucks * (F["secondary_truck_fixed_rs"] + F["secondary_truck_rs_per_km"] * fdf.district.map(dist.depot_to_district_km))
    ref["h7"] = {"forecast_total_t": round(float(fdf.forecast_t.sum()), 1),
                 "forecast_total_by_month": {m: round(float(fdf[fdf.month == m].forecast_t.sum()), 1) for m in FUT},
                 "plan_cost_rs": round(s7["objective"], 0), "plan_mip_gap": s7["mip_gap"], "secondary_trucks": int(fdf.trucks.sum()),
                 "secondary_cost_rs": round(float(fdf.sec_cost.sum()), 0),
                 "end_to_end_cost_rs": round(s7["objective"] + float(fdf.sec_cost.sum()), 0)}
    # wrong-chain example: forgetting the festival terms (used by the self-test to prove the error propagates)
    ref["meta"] = {"note": "ILLUSTRATIVE SYNTHETIC DATA", "seconds": round(time.time() - t0, 1)}
    json.dump(ref, open(H / "reference.json", "w"), indent=1, default=float)
    print(json.dumps({k: v for k, v in ref.items() if k != "h1"} | {"h1": {k: ref["h1"][k] for k in ("n_duplicate_rows", "n_bag_rows", "n_outlier_rows", "n_missing_district_months", "clean_total_tonnes")}}, indent=1, default=float))

if __name__ == "__main__":
    main()
