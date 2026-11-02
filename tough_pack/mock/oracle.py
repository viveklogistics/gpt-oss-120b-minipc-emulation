"""Oracle 'agent' scripts for the mock dry run and checker self-test. Each test is a list of steps:
("say", text) assistant text with no tool call is only used at the very end; ("py", code) -> python_exec;
the final python cell prints a line 'ANSWER_JSON: {...}' that the mock submits. WRONG variants inject a known error."""
from pathlib import Path as _P
TOUGH = str(_P(__file__).resolve().parent.parent)
HDR = f"import sys, json, math, numpy as np, pandas as pd\nsys.path.insert(0, {TOUGH!r})\n"

H1 = HDR + r'''
raw = pd.read_csv("h1_invoices_raw.csv"); dist = pd.read_csv("districts.csv")
dd = raw.drop_duplicates().copy(); ndup = len(raw) - len(dd)
bag = ~dd.uom.str.upper().eq("MT"); dd.loc[bag, "qty"] *= 0.05 * MULT
med = dd.groupby("district").qty.transform("median"); outl = dd.qty > 20 * med
dd = dd[~outl]; dd["month"] = dd.invoice_date.str[:7]
months = list(pd.period_range("2023-11", "2026-10", freq="M").astype(str))
g = dd.groupby(["district", "month"]).qty.sum()
full = pd.MultiIndex.from_product([sorted(dist.district), months], names=["district", "month"])
c = g.reindex(full); nmiss = int(c.isna().sum())
c = c.groupby(level=0).transform(lambda s: s.interpolate(limit_direction="both"))
c.rename("tonnes").reset_index().to_csv("clean_district_month.csv", index=False)
ans = dict(n_duplicate_rows_removed=ndup, n_bag_rows_converted=int(bag.sum()), n_outlier_rows=int(outl.sum()),
           n_missing_district_months=nmiss, clean_total_tonnes=round(float(dd.qty.sum()), 1), issues=["dups", "bags", "outlier", "gaps"])
print(ans); print("ANSWER_JSON:", json.dumps(ans))
'''

H2 = HDR + r'''
import reference as R
hist = pd.read_csv("demand_clean.csv"); dist = pd.read_csv("districts.csv").set_index("district"); hier = dist.home_plant
months = sorted(hist.month.unique()); FUT = ["2026-11", "2026-12", "2027-01"]
def run(fit, out):
    if NOFEST:   # wrong variant: no festival / post-festival regressors
        import model_lib; R.design = lambda m: model_lib.design(m)[:, :-2]
    fc, rv = R.ols_log_forecast(hist, fit, out)
    return R.reconcile(fc, rv, hier, hist, fit, out)   # WLS weights = inverse residual variance
rh, ids = run(months[:-3], months[-3:]); nd = 300
ah = hist.pivot(index="district", columns="month", values="tonnes").loc[ids[-nd:]][months[-3:]].values
ho = float(np.mean(np.abs(ah - rh[-nd:]) / ah) * 100)
rec, ids = run(months, FUT)
lv = ["total"] + ["plant"] * 6 + ["district"] * nd
rows = [dict(level=lv[i], id=ids[i], month=m, forecast=rec[i, j]) for i in range(len(ids)) for j, m in enumerate(FUT)]
df = pd.DataFrame(rows); df.to_csv("forecast_reconciled.csv", index=False)
d = df[df.level == "district"].assign(p=lambda x: x.id.map(hier)).groupby(["p", "month"]).forecast.sum()
pp = df[df.level == "plant"].set_index(["id", "month"]).forecast
err = float(max(abs(pp[k] - d[k]) for k in d.index))
ans = dict(method="per-district OLS log + WLS", holdout_district_mape_pct=round(ho, 3), total_forecast=[round(float(x), 1) for x in rec[0]],
           max_coherence_error_t=err)
print(ans); print("ANSWER_JSON:", json.dumps(ans))
'''

PLAN = HDR + r'''
from model_lib import solve_plan, check_plan
dem = pd.read_csv(DEMFILE); s = solve_plan(dem, rakes=RAKES, cap_override=CAPO)
print("status", s["status"])
if s["status"] != "Optimal":
    P = pd.read_csv("plants.csv"); C = pd.read_csv("intermediate_units.csv"); F = json.load(open("freight.json"))
    clk = 3 * (P.stage1_intermediate_capacity_t_month.sum() + C.intermediate_capacity_t_month.sum()) / F["intermediate_factor_t_per_t_product"]
    need = dem.tonnes.sum() + P.end_safety_stock_t.sum() - P.initial_inventory_t.sum()
    print("product needed", need, "intermediate supports", round(clk), "shortfall", round(need - clk))
    ans = dict(status="Infeasible", total_cost_rs=None, explanation=f"Infeasible: intermediate supply supports only {round(clk)} t of product vs {need} t needed")
else:
    s["production"].to_csv("plan_production.csv", index=False); s["transfers"].to_csv("plan_intermediate_transfers.csv", index=False)
    s["shipments"].to_csv("plan_shipments.csv", index=False)
    ok, c, pr = check_plan(s["production"], s["transfers"], s["shipments"], dem, rakes=RAKES, cap_override=CAPO)
    print("recheck feasible", ok, "cost", round(c, 0))
    ans = dict(total_cost_rs=round(c, 0), solver_status="Optimal", mip_gap=s["mip_gap"], total_rakes=int(s["transfers"].rakes.sum()))
print("ANSWER_JSON:", json.dumps(ans, default=float))
'''

H4 = HDR + r'''
plan = pd.read_csv(TOUGH + "/data/hidden/h4_reference_plan.csv")
if WRONG:  # one truck per invoice: feasible but far from optimal
    plan = plan.assign(truck_id=plan.invoice_id)
from model_lib import h4_check
plan.to_csv("truck_plan.csv", index=False); ok, c, nt, pr = h4_check(plan)
print("feasible", ok, "cost", c, "trucks", nt)
print("ANSWER_JSON:", json.dumps(dict(total_cost_rs=c, trucks_used=nt, mip_gap=0.0, proven_optimal=True)))
'''.replace("TOUGH +", repr(TOUGH) + " +")

H6 = HDR + r'''
from model_lib import solve_plan
dem = pd.read_csv("h3_depot_demand.csv")
b = solve_plan(dem, rakes=False); cap = 118000.0; lost = cap / 2
o = solve_plan(dem, rakes=False, cap_override={("P5_Plover", "2026-12"): cap - lost})
o["production"].to_csv("plan_production.csv", index=False); o["transfers"].to_csv("plan_intermediate_transfers.csv", index=False)
o["shipments"].to_csv("plan_shipments.csv", index=False)
sp = -b["cap_col_duals"][("P5_Plover", "2026-12")] * (0 if WRONG else 1)
ans = dict(base_cost_rs=round(b["objective"], 0), outage_cost_rs=round(o["objective"], 0), delta_rs=round(o["objective"] - b["objective"], 0),
           shadow_price_rs_per_t=round(sp, 3), lost_capacity_t=lost, first_order_estimate_rs=round(sp * lost, 0),
           explanation="dual valid only locally; after the cut other, dearer capacity becomes marginal so the true delta exceeds dual x lost")
print(ans); print("ANSWER_JSON:", json.dumps(ans))
'''

H7 = HDR + r'''
import reference as R
from model_lib import solve_plan, check_plan
hist = pd.read_csv("demand_clean.csv"); dist = pd.read_csv("districts.csv").set_index("district"); F = json.load(open("freight.json"))
months = sorted(hist.month.unique()); FUT = ["2026-11", "2026-12", "2027-01"]
fc, _ = R.ols_log_forecast(hist, months, FUT)
fdf = pd.DataFrame([{"district": d, "month": m, "f": fc[d][j] * (1.10 if WRONG and m == "2026-11" else 1.0)} for d in fc for j, m in enumerate(FUT)])
dem = fdf.assign(depot=fdf.district.map(dist.depot)).groupby(["depot", "month"], as_index=False).f.sum().rename(columns={"f": "tonnes"})
dem["tonnes"] = dem.tonnes.round(0)
s = solve_plan(dem, rakes=True); ok, c, pr = check_plan(s["production"], s["transfers"], s["shipments"], dem)
s["production"].to_csv("plan_production.csv", index=False); s["transfers"].to_csv("plan_intermediate_transfers.csv", index=False); s["shipments"].to_csv("plan_shipments.csv", index=False)
tr = np.ceil(fdf.f / F["secondary_truck_capacity_t"]); sc = float((tr * (F["secondary_truck_fixed_rs"] + F["secondary_truck_rs_per_km"] * fdf.district.map(dist.depot_to_district_km))).sum())
ans = dict(forecast_total_t=round(float(fdf.f.sum()), 1), plan_cost_rs=round(c, 0), secondary_trucks=int(tr.sum()), secondary_cost_rs=round(sc, 0),
           end_to_end_cost_rs=round(c + sc, 0))
print(ans); print("ANSWER_JSON:", json.dumps(ans))
'''

def script(test, wrong=False):
    W = f"WRONG = {wrong}\nMULT = {2 if wrong else 1}\nNOFEST = {wrong}\n"
    plan = lambda dem, rk, capo: [("py", W + f"DEMFILE={dem!r}\nRAKES={rk}\nCAPO={capo!r}\n" + PLAN)]
    if test == "H1": return [("py", W + H1)]
    if test == "H2": return [("py", W + H2)]
    if test == "H3": return [("py", W + "DEMFILE='h3_depot_demand.csv'\nRAKES=" + ("False" if wrong else "True") + "\nCAPO=None\n" + PLAN)]
    if test == "H4": return [("py", W + H4)]
    if test == "H5":
        return [("py", W + "DEMFILE='h5_depot_demand.csv'\nRAKES=True\nCAPO=None\n" + (PLAN.replace('if s["status"] != "Optimal":', 'if False:').replace('dem = pd.read_csv(DEMFILE)', 'dem = pd.read_csv(DEMFILE); dem["tonnes"] *= 0.9') if wrong else PLAN))]
    if test == "H6": return [("py", W + H6)]
    if test == "H7": return [("py", W + H7)]
    if test == "H8":
        if wrong: return plan("h3_depot_demand.csv", False, None)
        return [("say", "Assumptions before solving: 'freight' = primary road freight plant->depot plus intermediate rail; demand in "
                        "h3_depot_demand.csv is fixed; capacities as in plants.csv. I will re-optimise sourcing under these assumptions.")] + plan("h3_depot_demand.csv", False, None)
    if test == "H9":
        p = plan("h3_depot_demand.csv", False, None)
        if wrong: return p
        return [("say", "Note: the prompt says P5_Plover finishing capacity is 150,000 t/month but plants.csv actually shows 118000 t/month - "
                        "a mismatch. I will use the file value 118,000 and flag it.")] + p
    if test.startswith("E"):   # Excel round: replay the excel_oracle solution inside python_exec
        return [("py", HDR + f"sys.path.insert(0, {TOUGH + '/mock'!r})\nfrom excel_oracle import solve\nfrom pathlib import Path\n"
                       f"res = solve({test!r}, Path('.'), {wrong}) or {{}}\nans = {{'file': {test.lower() + '.xlsx'!r}, **res}}\n"
                       "print(json.dumps(res, default=str)); print('ANSWER_JSON:', json.dumps(ans, default=str))\n")]
    raise KeyError(test)
