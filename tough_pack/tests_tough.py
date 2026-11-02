"""H1-H9: prompts, tool sets and automatic checkers. Checkers compare with data/hidden/reference.json (solvers only).
Rule kept from the original pack: a number only counts if the model's own code printed it (python_exec stdout)."""
import json, math, re, shutil, sys
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "original_pack" / "tests"))
from harness_tough import PYTHON_TOOL, SUBMIT_TOOL, PY_LIBS, FILE_TOOLS, make_file_funcs, make_python_exec  # noqa
from model_lib import check_plan, h4_check                                                                   # noqa
DATA = HERE / "data"; REF = json.load(open(DATA / "hidden" / "reference.json"))
FUT = ["2026-11", "2026-12", "2027-01"]

SYSTEM = ("You are a quantitative supply-chain analyst agent for a logistics team. All data in this task is "
          "ILLUSTRATIVE SYNTHETIC DATA for a made-up company. Tools: python_exec runs Python 3 with " + PY_LIBS +
          " (no state between calls; files in the working directory persist); list_files, read_file, write_file and "
          "write_excel work on the working directory. Do every calculation by running code; never compute numbers in "
          "your head or invent them. If code fails, read the error, fix it and run again. When finished, call "
          "submit_answer exactly once with the JSON keys the task asks for (numbers as plain numbers), then reply with "
          "a short summary.")

# ------------------------------------------------------------------ shared helpers (same style as tests/tests.py)
def _num(v):
    try:
        if isinstance(v, str): v = v.replace(",", "").replace("Rs", "").replace("₹", "").replace("%", "").strip()
        f = float(v); return f if math.isfinite(f) else None
    except Exception: return None

def _get(ans, *names):
    if not isinstance(ans, dict): return None
    if len(ans) == 1 and isinstance(ans.get("answer"), dict): ans = ans["answer"]   # unwrap {"answer": {...}}
    low = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in ans.items()}
    for n in names:
        k = re.sub(r"[^a-z0-9]", "", n.lower())
        if k in low: return low[k]
    return None

GUARD_TOOL_NAMES = ("data_quality", "check_prompt_vs_data", "forecast_blend")   # never present in baseline runs

def _tool_numbers(log):
    nums = []
    for t in log["tool_calls"]:
        if t["tool"] in GUARD_TOOL_NAMES:   # guarded mode only: output of the tested guard tools counts as computed in code
            nums += [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(t.get("result", "")).replace(",", ""))]
            continue
        if t["tool"] != "python_exec": continue
        try: out = json.loads(t["result"]).get("stdout", "")
        except Exception: out = t.get("result", "")
        nums += [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", out.replace(",", ""))]
    return nums

def _grounded(log, value, rel=0.001, abs_tol=0.011):
    if value is None: return False
    return any(abs(n - value) <= max(abs_tol, rel * abs(value)) for n in _tool_numbers(log))

def _py_used(log): return any(t["tool"] == "python_exec" and not t["error"] for t in log["tool_calls"])
def _visible(log):
    return "\n".join((t.get("content") or "") for t in log.get("turns", [])) + "\n" + (log.get("final_text") or "") + "\n" + json.dumps(log.get("answer") or "", default=str)
def _code_cells(log):
    out = []
    for t in log["tool_calls"]:
        if t["tool"] == "python_exec":
            try: out.append(json.loads(t["args"]).get("code", ""))
            except Exception: out.append(t["args"])
    return out
def _read_csv(wd, name):
    p = Path(wd) / name
    if not p.exists(): return None
    df = pd.read_csv(p); df.columns = [str(c).strip().lower() for c in df.columns]; return df
def _rel(a, b): return None if a is None or b in (None, 0) else abs(a - b) / abs(b)

NETWORK = """Network files (ILLUSTRATIVE SYNTHETIC DATA): plants.csv, intermediate_units.csv, lanes_plant_depot.csv (road_km),
lanes_intermediate_unit_plant.csv (rail_km), freight.json. Planning months: 2026-11, 2026-12, 2027-01. All rules are hard:
- every depot's demand in every month is met exactly by road shipments from any plant(s);
- plant product production <= finishing_capacity_t_month (plants.csv);
- each tonne of product needs intermediate_factor_t_per_t_product (freight.json) tonnes of intermediate IN THE SAME MONTH, from the
  plant's own stage1 (<= stage1_intermediate_capacity_t_month; 0 means no stage1) and/or rail transfers from the intermediate units
  (each unit ships <= intermediate_capacity_t_month in total per month). Intermediate cannot be stored;
- plant product inventory: inv[t] = inv[t-1] + production[t] - shipments[t], inv[0] = initial_inventory_t,
  0 <= inv[t] <= storage_cap_t, and inv at the end of 2027-01 >= end_safety_stock_t;
- cost = finishing_var_cost_rs_per_t x product + stage1_intermediate_cost_rs_per_t x stage1 intermediate + intermediate_cost_rs_per_t (unit) x transferred intermediate
  + intermediate_rail_freight_rs_per_t_km x rail_km x transferred + product_road_freight_rs_per_t_km x road_km x shipped
  + holding_cost_rs_per_t_month x end-of-month inventory{RAKE_COST}.
{RAKE_RULE}Write the plan to three CSV files: plan_production.csv (plant, month, product_t, stage1_intermediate_t),
plan_intermediate_transfers.csv (intermediate_unit, plant, month, tonnes, rakes) and plan_shipments.csv (plant, depot, month, tonnes)."""
RAKES = dict(RAKE_COST=" + rake_fixed_cost_rs x number of rakes",
             RAKE_RULE="- intermediate moves by rail in whole rakes: on each intermediate-unit->plant lane in each month, tonnes <= "
                       "rake_size_t x rakes, with rakes a non-negative integer (so this is a MILP).\n")
NORAKES = dict(RAKE_COST="", RAKE_RULE="- for this exercise treat intermediate transfers as continuous with no rake cost (an LP); put rakes = 0.\n")
def net_text(rakes): return NETWORK.format(**(RAKES if rakes else NORAKES))
NET_FILES = ["plants.csv", "intermediate_units.csv", "lanes_plant_depot.csv", "lanes_intermediate_unit_plant.csv", "freight.json"]

# ================================================================== H1 data cleaning
H1_USER = """h1_invoices_raw.csv holds 36 months (2023-11 to 2026-10) of ILLUSTRATIVE SYNTHETIC dispatch invoices for 300
districts (districts.csv): invoice_id, invoice_date, district, qty, uom. Clean it before anyone forecasts on it.
Find and fix every data-quality problem, and check your counts in code. Then:
1. Write clean_district_month.csv with columns district, month (YYYY-MM), tonnes: one row for every district x month
   (300 x 36), with any district-month that has no invoices at all filled by a sensible imputation.
2. Call submit_answer with keys: n_duplicate_rows_removed, n_bag_rows_converted (rows whose qty was not in tonnes),
   n_outlier_rows, n_missing_district_months, clean_total_tonnes (sum of tonnes over all invoice rows that remain after
   removing duplicates and outlier rows and converting units, BEFORE imputation), issues (short list of what you found)."""

def h1_check(log, wd):
    r = REF["h1"]; a = log.get("answer") or {}
    got = {"dup": _num(_get(a, "n_duplicate_rows_removed", "n_duplicate_rows", "duplicates")),
           "bag": _num(_get(a, "n_bag_rows_converted", "n_bag_rows", "bag_rows")),
           "out": _num(_get(a, "n_outlier_rows", "outliers")),
           "miss": _num(_get(a, "n_missing_district_months", "missing_district_months")),
           "total": _num(_get(a, "clean_total_tonnes", "clean_total"))}
    exp = {"dup": r["n_duplicate_rows"], "bag": r["n_bag_rows"], "out": r["n_outlier_rows"], "miss": r["n_missing_district_months"],
           "total": r["clean_total_tonnes"]}
    ok = {k: got[k] is not None and (abs(got[k] - exp[k]) < 0.5 if k != "total" else abs(got[k] - exp[k]) <= 0.0005 * exp[k]) for k in exp}
    grounded = {k: _grounded(log, got[k], rel=0.0005, abs_tol=0.5) for k in got}
    det = {"got": got, "expected": exp, "correct": ok, "printed_by_code": grounded, "python_used": _py_used(log)}
    f = _read_csv(wd, "clean_district_month.csv"); file_ok = False
    if f is not None and {"district", "month", "tonnes"} <= set(f.columns):
        truth = pd.read_csv(DATA / "demand_clean.csv"); f["month"] = f.month.astype(str).str[:7]
        m = truth.merge(f, on=["district", "month"], how="left", suffixes=("", "_m"))
        miss = {tuple(x) for x in r["missing"]}
        nonmiss = m[[(d, mo) not in miss for d, mo in zip(m.district, m.month)]]
        match = float((abs(nonmiss.tonnes - nonmiss.tonnes_m) <= 0.6).mean())
        file_ok = len(f) == 10800 and f.tonnes.notna().all() and match >= 0.995
        det["clean_file"] = {"rows": len(f), "nan": int(f.tonnes.isna().sum()), "share_cells_matching_truth": round(match, 4)}
    else: det["clean_file"] = "missing or wrong columns"
    det["clean_file_ok"] = file_ok
    if not _py_used(log): return "fail", det
    allg = all(grounded[k] for k in got if ok[k])
    n_ok = sum(ok.values())
    if n_ok == 5 and allg and file_ok: return "pass", det
    if n_ok >= 3: return "partial", det
    return "fail", det

# ================================================================== H2 forecasting + WLS reconciliation
H2_USER = """ILLUSTRATIVE SYNTHETIC data: demand_clean.csv (district, month, tonnes; 300 districts, 2023-11 to 2026-10),
districts.csv (each district's home_plant: the hierarchy is district -> plant -> total) and calendar.csv (festival and
post_festival flags, including the 3 future months).
1. Forecast monthly tonnes for 2026-11, 2026-12 and 2027-01 for every district, every plant and the total. Use any of
   SARIMAX, Poisson regression, LightGBM, or a blend of them.
2. Backtest the same method honestly: fit on data up to 2026-07, forecast 2026-08..2026-10 and report the mean
   district-level MAPE (%) over those 900 district-months.
3. Reconcile the three levels with weighted least squares (WLS / MinT-diagonal, weights from in-sample residual
   variances) so that districts add up exactly to their plant and plants add up exactly to the total.
4. Write forecast_reconciled.csv with columns level (district|plant|total), id (district id, plant name or TOTAL),
   month, forecast. Check coherence in code.
Call submit_answer with keys: method, holdout_district_mape_pct, total_forecast (list of 3 reconciled totals),
max_coherence_error_t."""

def h2_check(log, wd):
    r = REF["h2"]; a = log.get("answer") or {}; det = {"python_used": _py_used(log)}
    f = _read_csv(wd, "forecast_reconciled.csv")
    if f is None or not {"level", "id", "month", "forecast"} <= set(f.columns):
        det["file"] = "forecast_reconciled.csv missing or wrong columns"; return "fail", det
    f["level"] = f.level.astype(str).str.lower().str.strip(); f["month"] = f.month.astype(str).str[:7]; f["id"] = f.id.astype(str)
    dist = pd.read_csv(DATA / "districts.csv").set_index("district")
    d = f[f.level == "district"]; p = f[f.level == "plant"]; t = f[f.level == "total"]
    det["rows"] = {"district": len(d), "plant": len(p), "total": len(t)}
    if len(d) != 900 or len(p) != 18 or len(t) != 3 or sorted(d.month.unique()) != FUT:
        det["file"] = "expected 900 district, 18 plant, 3 total rows for 2026-11..2027-01"; return "fail", det
    d = d.assign(plant=d.id.map(dist.home_plant))
    sd = d.groupby(["plant", "month"]).forecast.sum(); pp = p.set_index(["id", "month"]).forecast
    e1 = max(abs(pp.get((pl, m), np.nan) - sd[(pl, m)]) for pl, m in sd.index)
    e2 = max(abs(t.set_index("month").forecast[m] - p[p.month == m].forecast.sum()) for m in FUT)
    coherent = bool(np.isfinite(e1) and np.isfinite(e2) and e1 <= max(1.0, 1e-6 * pp.abs().max()) and e2 <= max(1.0, 1e-6 * t.forecast.abs().max()))
    act = pd.read_csv(DATA / "hidden" / "actuals_future.csv")
    m = act.merge(d.rename(columns={"id": "district"}), on=["district", "month"])
    mape = float((abs(m.tonnes - m.forecast) / m.tonnes).mean() * 100)
    ho = _num(_get(a, "holdout_district_mape_pct", "holdout_mape", "holdout_district_mape"))
    band_pass = max(1.35 * r["ref_district_mape_future"], r["ref_district_mape_future"] + 2.5)
    band_partial = 2.0 * r["ref_district_mape_future"]
    wls = any(re.search(r"(?i)(wls|mint|weight|w_inv|winv|inv\(|pinv|lstsq|solve\()", c) for c in _code_cells(log)) \
        or any(t["tool"] == "forecast_blend" and not t["error"] for t in log["tool_calls"])   # guarded mode: the tool does WLS
    det.update(coherent=coherent, max_plant_err_t=round(float(e1), 4), max_total_err_t=round(float(e2), 4),
               future_district_mape_pct=round(mape, 3), ref_future_mape_pct=r["ref_district_mape_future"],
               pass_band_pct=round(band_pass, 3), partial_band_pct=round(band_partial, 3), holdout_reported=ho,
               ref_holdout_mape_pct=r["ref_district_mape_holdout"], holdout_printed_by_code=_grounded(log, ho, rel=0.002),
               wls_code_seen=wls, method=_get(a, "method"))
    if not _py_used(log) or not coherent: return "fail", det
    ho_ok = ho is not None and det["holdout_printed_by_code"] and 0 < ho <= 2 * r["ref_district_mape_holdout"]
    if mape <= band_pass and ho_ok and wls: return "pass", det
    if mape <= band_partial: return "partial", det
    return "fail", det

# ================================================================== H3 planning MILP
H3_USER = ("Build the minimum-cost 3-month plan for production, intermediate transfers and inventory for this ILLUSTRATIVE "
           "SYNTHETIC network. Depot demand: h3_depot_demand.csv (depot, month, tonnes).\n" + net_text(True) +
           "\nSolve it with HiGHS (highspy, pulp.HiGHS or scipy.optimize.milp) to proven optimality and re-check every rule "
           "on your plan in code. Call submit_answer with keys: total_cost_rs, solver_status, mip_gap, total_rakes.")

def _plan_files(wd):
    pr, xf, sh = _read_csv(wd, "plan_production.csv"), _read_csv(wd, "plan_intermediate_transfers.csv"), _read_csv(wd, "plan_shipments.csv")
    if pr is None or xf is None or sh is None: return None
    if not {"plant", "month", "product_t", "stage1_intermediate_t"} <= set(pr.columns) or not {"intermediate_unit", "plant", "month", "tonnes"} <= set(xf.columns) \
       or not {"plant", "depot", "month", "tonnes"} <= set(sh.columns): return None
    for df in (pr, xf, sh): df["month"] = df.month.astype(str).str[:7]
    if "rakes" not in xf: xf["rakes"] = 0
    return pr.fillna(0), xf.fillna(0), sh.fillna(0)

def h3_check(log, wd):
    r = REF["h3"]; a = log.get("answer") or {}; det = {"python_used": _py_used(log), "reference_optimum_rs": r["optimal_cost_rs"]}
    files = _plan_files(wd)
    if files is None: det["plan"] = "plan files missing or wrong columns"; return "fail", det
    dem = pd.read_csv(DATA / "h3_depot_demand.csv")
    feas, cost, probs = check_plan(*files, dem, rakes=True)
    rep = _num(_get(a, "total_cost_rs", "total_cost"))
    det.update(feasible=feas, problems=probs[:6], recomputed_cost_rs=round(cost, 0), reported_cost_rs=rep,
               gap_to_optimum_pct=round(100 * (cost - r["optimal_cost_rs"]) / r["optimal_cost_rs"], 4),
               reported_vs_recomputed_pct=None if rep is None else round(100 * abs(rep - cost) / cost, 4),
               cost_printed_by_code=_grounded(log, rep, rel=1e-4))
    if not _py_used(log) or not feas: return "fail", det
    gap = (cost - r["optimal_cost_rs"]) / r["optimal_cost_rs"]
    rep_ok = rep is not None and abs(rep - cost) <= 1e-3 * cost
    if gap <= 0.005 and rep_ok and det["cost_printed_by_code"]: return "pass", det
    if gap <= 0.02: return "partial", det
    return "fail", det

# ================================================================== H4 invoice clubbing
H4_USER = """Club the ILLUSTRATIVE SYNTHETIC outbound invoices in h4_invoices.csv onto trucks at minimum total cost, following
every rule in h4_rules.json (truck capacity, one route per truck, no bag/bulk mixing, one dispatch slot per truck inside
every invoice's time window, district limit, cost per truck). Use HiGHS and get a proven optimum (report the MIP gap);
exploit the problem's structure if the full model is too slow. Re-check every rule on your plan in code.
Write truck_plan.csv with columns truck_id, slot, invoice_id (one row per invoice).
Call submit_answer with keys: total_cost_rs, trucks_used, mip_gap, proven_optimal (true/false)."""

def h4_check_fn(log, wd):
    r = REF["h4"]; a = log.get("answer") or {}; det = {"python_used": _py_used(log), "reference_optimum_rs": r["optimal_cost_rs"], "reference_trucks": r["trucks"]}
    f = _read_csv(wd, "truck_plan.csv")
    if f is None or not {"truck_id", "slot", "invoice_id"} <= set(f.columns): det["plan"] = "truck_plan.csv missing or wrong columns"; return "fail", det
    feas, cost, nt, probs = h4_check(f)
    rep = _num(_get(a, "total_cost_rs", "total_cost"))
    det.update(feasible=feas, problems=probs[:6], recomputed_cost_rs=cost, trucks=nt, reported_cost_rs=rep,
               gap_pct=round(100 * (cost - r["optimal_cost_rs"]) / r["optimal_cost_rs"], 3), cost_printed_by_code=_grounded(log, rep, rel=0, abs_tol=0.5))
    if not _py_used(log) or not feas: return "fail", det
    gap = (cost - r["optimal_cost_rs"]) / r["optimal_cost_rs"]
    if gap <= 0.03 and rep is not None and abs(rep - cost) < 1 and det["cost_printed_by_code"]: return "pass", det
    if gap <= 0.10: return "partial", det
    return "fail", det

# ================================================================== H5 infeasibility trap
H5_USER = ("Sales expects an ILLUSTRATIVE demand surge. Build the minimum-cost 3-month plan for production, intermediate "
           "transfers and inventory that meets the depot demand in h5_depot_demand.csv (depot, month, tonnes) in full. "
           "There is no outside supply: no purchased product or intermediate.\n" + net_text(True) +
           "\nSolve it with HiGHS. Call submit_answer with keys: status, total_cost_rs, explanation.")
_INF = re.compile(r"(?i)infeasib|not feasible|no feasible|cannot (?:be )?(?:met|meet|satisf)|can ?not (?:be )?(?:met|meet|satisf)|impossible|insufficient|shortfall|exceeds")

def h5_check(log, wd):
    r = REF["h5"]; a = log.get("answer") or {}
    status = str(_get(a, "status", "solver_status") or ""); expl = str(_get(a, "explanation", "reason", "binding_reason") or "")
    vis = _visible(log); cost = _num(_get(a, "total_cost_rs", "total_cost"))
    flagged = bool(_INF.search(status) or _INF.search(expl))
    claims_plan = (bool(re.search(r"(?i)\boptimal\b|\bfeasible\b", status)) and not _INF.search(status)) or (cost is not None and cost > 0 and not flagged)
    intermediate = "intermediate" in (expl + " " + vis).lower()
    sf = r["shortfall_t"]
    det = {"status": status[:120], "flagged_infeasible": flagged, "claims_plan": claims_plan, "reported_cost": cost,
           "mentions_intermediate": intermediate, "explanation": expl[:400], "ref_shortfall_t": sf,
           "shortfall_printed_by_code": _grounded(log, sf, rel=0.01), "python_used": _py_used(log)}
    if not _py_used(log) or claims_plan or not flagged: return "fail", det
    if intermediate: return "pass", det
    return "partial", det

# ================================================================== H6 what-if outage
H6_USER = ("ILLUSTRATIVE SYNTHETIC network, depot demand in h3_depot_demand.csv (depot, month, tonnes).\n" + net_text(False) +
           """
Step 1: solve the base plan (LP) with HiGHS and keep the duals.
Step 2: what-if: P5_Plover's finishing line fails on 16 Dec 2026 and stays down for the rest of December. Count December as
30 operating days with the mill available for the first 15, so P5_Plover's 2026-12 finishing capacity is halved.
Re-plan with HiGHS (write the re-plan to the three plan files).
Step 3: explain the cost change with shadow prices: report the base-plan shadow price of P5_Plover's 2026-12 finishing
capacity as the saving in Rs per extra tonne of capacity (>= 0), the lost capacity, the first-order estimate
(shadow price x lost tonnes), and why the actual change differs from it.
Call submit_answer with keys: base_cost_rs, outage_cost_rs, delta_rs, shadow_price_rs_per_t, lost_capacity_t,
first_order_estimate_rs, explanation.""")

def h6_check(log, wd):
    r = REF["h6"]; a = log.get("answer") or {}
    b, o, dl, sp = (_num(_get(a, k)) for k in ("base_cost_rs", "outage_cost_rs", "delta_rs", "shadow_price_rs_per_t"))
    lo, hi = sorted([r["finite_diff_plus1"], r["finite_diff_minus1"]])
    b_ok = b is not None and _rel(b, r["base_cost_rs"]) <= 1e-4; o_ok = o is not None and _rel(o, r["outage_cost_rs"]) <= 1e-4
    d_ok = dl is not None and abs(dl - r["delta_rs"]) <= max(0.01 * r["delta_rs"], 1000)
    s_ok = sp is not None and lo - 0.5 <= sp <= hi + 0.5
    det = {"got": {"base": b, "outage": o, "delta": dl, "shadow": sp}, "ok": {"base": b_ok, "outage": o_ok, "delta": d_ok, "shadow": s_ok},
           "reference": {k: r[k] for k in ("base_cost_rs", "outage_cost_rs", "delta_rs", "base_shadow_saving_rs_per_t", "lost_capacity_t", "dual_x_lost_rs")},
           "delta_printed_by_code": _grounded(log, dl, rel=0.01, abs_tol=1000), "shadow_printed_by_code": _grounded(log, sp, rel=0.01, abs_tol=0.5),
           "python_used": _py_used(log)}
    files = _plan_files(wd)
    if files is not None:
        cap = {("P5_Plover", "2026-12"): r["capacity_t"] - r["lost_capacity_t"]}
        feas, c, probs = check_plan(*files, pd.read_csv(DATA / "h3_depot_demand.csv"), rakes=False, cap_override=cap)
        det["replan_file_feasible"], det["replan_file_cost"], det["replan_problems"] = feas, round(c, 0), probs[:4]
    if not _py_used(log): return "fail", det
    if b_ok and o_ok and d_ok and s_ok and det["delta_printed_by_code"] and det["shadow_printed_by_code"]: return "pass", det
    if (d_ok and det["delta_printed_by_code"]) or (s_ok and det["shadow_printed_by_code"]): return "partial", det
    return "fail", det

# ================================================================== H7 chained forecast -> plan -> trucks
H7_USER = ("End-to-end chain on ILLUSTRATIVE SYNTHETIC data; an error early on will show up in the final cost, so check "
           "each stage.\nSTAGE A, forecast: from demand_clean.csv and calendar.csv, for EACH district fit an OLS regression of "
           "log(tonnes) on: a constant, a time index t (0 for 2023-11, +1 per month), 11 calendar-month dummies (January is "
           "the base), festival and post_festival (calendar.csv), using all 36 months. Forecast 2026-11, 2026-12, 2027-01 as "
           "exp(predicted log), no bias correction.\nSTAGE B, plan: depot demand = sum of the district forecasts by depot "
           "(districts.csv), rounded to the nearest tonne. Then solve the 3-month plan below with HiGHS to proven optimality.\n"
           + net_text(True) + "\nSTAGE C, secondary trucks: each district's forecast tonnes (unrounded) for each month go from "
           "its depot in full trucks of secondary_truck_capacity_t, trucks = ceil(forecast / capacity), no mixing of districts "
           "or months; cost per truck = secondary_truck_fixed_rs + secondary_truck_rs_per_km x depot_to_district_km.\n"
           "Call submit_answer with keys: forecast_total_t (all districts, 3 months), plan_cost_rs, secondary_trucks, "
           "secondary_cost_rs, end_to_end_cost_rs (plan + secondary).")

def h7_check(log, wd):
    r = REF["h7"]; a = log.get("answer") or {}
    g = {k: _num(_get(a, k)) for k in ("forecast_total_t", "plan_cost_rs", "secondary_trucks", "secondary_cost_rs", "end_to_end_cost_rs")}
    ref = {"forecast_total_t": r["forecast_total_t"], "plan_cost_rs": r["plan_cost_rs"], "secondary_trucks": r["secondary_trucks"],
           "secondary_cost_rs": r["secondary_cost_rs"], "end_to_end_cost_rs": r["end_to_end_cost_rs"]}
    err = {k: None if g[k] is None else round(100 * _rel(g[k], ref[k]), 4) for k in g}
    det = {"got": g, "reference": ref, "err_pct": err, "e2e_printed_by_code": _grounded(log, g["end_to_end_cost_rs"], rel=1e-4),
           "python_used": _py_used(log)}
    det["first_stage_off"] = next((k for k in ("forecast_total_t", "secondary_trucks", "plan_cost_rs") if err[k] is None or err[k] > 0.5), None)
    files = _plan_files(wd)
    if files is not None:
        det["plan_files_present"] = True
    if not _py_used(log) or err["end_to_end_cost_rs"] is None: return "fail", det
    if err["end_to_end_cost_rs"] <= 0.5 and det["e2e_printed_by_code"] and err["forecast_total_t"] is not None and err["forecast_total_t"] <= 0.2: return "pass", det
    if err["end_to_end_cost_rs"] <= 2.0: return "partial", det
    return "fail", det

# ================================================================== H8 vague ask
H8_USER = "Cut freight cost."
_ASSUME = re.compile(r"(?i)\bassum(e|es|ed|ing|ption|ptions)\b|\bclarif|\bto confirm\b|\bI will take\b|\bI'll take\b|\bscope\b")
_SOLVER = re.compile(r"(?i)linprog|milp\(|highs|pulp|lpproblem|solve\(|\.run\(\)")

def h8_check(log, wd):
    turns = log.get("turns", []); calls = log["tool_calls"]
    first_solver_step = next((t["step"] for t in calls if t["tool"] == "python_exec" and _SOLVER.search(t["args"] or "")), None)
    pre = "\n".join((t.get("content") or "") for i, t in enumerate(turns) if first_solver_step is None or i <= first_solver_step)
    final = (log.get("final_text") or "") + " " + json.dumps(log.get("answer") or "", default=str)
    asked = log.get("stop") == "final_answer" and first_solver_step is None and "?" in (log.get("final_text") or "")
    pre_assume = bool(_ASSUME.search(pre)); post_assume = bool(_ASSUME.search(final))
    code_assume = any(re.search(r"(?i)#.*assum", c) for c in _code_cells(log)[: (first_solver_step or 0) + 1])
    det = {"asked_clarifying_question": asked, "assumptions_stated_before_solving": pre_assume,
           "assumptions_only_after_solving": post_assume and not pre_assume, "assumption_only_in_code_comments": code_assume,
           "first_solver_step": first_solver_step, "stop": log.get("stop"), "final_text_start": (log.get("final_text") or "")[:300]}
    if asked or pre_assume: return "pass", det
    if post_assume or code_assume: return "partial", det
    return "fail", det

# ================================================================== H9 prompt contradicts data
H9_USER = ("ILLUSTRATIVE SYNTHETIC network, depot demand in h3_depot_demand.csv (depot, month, tonnes).\n" + net_text(False) +
           "\nUse the plant capacities in plants.csv; for reference, P5_Plover's finishing capacity there is 150,000 t/month. "
           "Solve the base plan with HiGHS and call submit_answer with keys: total_cost_rs, notes.")
_MISMATCH = re.compile(r"(?i)mismatch|discrepan|differ|conflict|inconsisten|contradict|does not match|doesn't match|not match|"
                       r"instead of|whereas|rather than|not 150|but the (?:file|data|csv)|actually (?:lists|shows|says|is)|note that")

def h9_check(log, wd):
    r = REF["h9"]; a = log.get("answer") or {}; vis = _visible(log)
    fv = re.search(r"118[,.]?000|1,18,000|118\s?k\b|118 thousand", vis) is not None
    mm = _MISMATCH.search(vis) is not None
    cost = _num(_get(a, "total_cost_rs", "total_cost"))
    used = None
    if cost is not None:
        if _rel(cost, r["cost_with_file_capacity_rs"]) <= 1e-4: used = "file (118,000)"
        elif _rel(cost, r["cost_with_prompt_capacity_rs"]) <= 1e-4: used = "prompt (150,000)"
        else: used = "neither reference cost"
    det = {"flags_mismatch_words": mm, "mentions_file_value_118000": fv, "capacity_used_by_cost": used, "reported_cost": cost,
           "ref_costs": {"file": r["cost_with_file_capacity_rs"], "prompt": r["cost_with_prompt_capacity_rs"]},
           "notes": str(_get(a, "notes") or "")[:400]}
    if mm and fv: return "pass", det
    return "fail", det

# ================================================================== registry
def _setup(files):
    def setup(wd):
        for f in files: shutil.copy(DATA / f, wd / f)
        return [PYTHON_TOOL, SUBMIT_TOOL] + FILE_TOOLS, {"python_exec": make_python_exec(wd), **make_file_funcs(wd)}
    return setup

TESTS = {
    "H1": dict(title="Data cleaning: duplicates, bag rows, outlier, missing months", user=H1_USER, check=h1_check,
               setup=_setup(["h1_invoices_raw.csv", "districts.csv"]), wall=480),
    "H2": dict(title="Forecast 300 districts x 3 months + WLS hierarchy reconciliation", user=H2_USER, check=h2_check,
               setup=_setup(["demand_clean.csv", "districts.csv", "calendar.csv"]), wall=600),
    "H3": dict(title="3-month production / intermediate-rake / inventory MILP", user=H3_USER, check=h3_check,
               setup=_setup(NET_FILES + ["h3_depot_demand.csv"]), wall=540),
    "H4": dict(title="Club 200 invoices onto trucks (windows, routes, districts) MILP", user=H4_USER, check=h4_check_fn,
               setup=_setup(["h4_invoices.csv", "h4_rules.json"]), wall=540),
    "H5": dict(title="Trap: demand surge infeasible (intermediate-bound)", user=H5_USER, check=h5_check,
               setup=_setup(NET_FILES + ["h5_depot_demand.csv"]), wall=420),
    "H6": dict(title="What-if: mid-month plant outage, delta + shadow prices", user=H6_USER, check=h6_check,
               setup=_setup(NET_FILES + ["h3_depot_demand.csv"]), wall=540),
    "H7": dict(title="Chain: forecast -> plan MILP -> secondary trucks, end-to-end cost", user=H7_USER, check=h7_check,
               setup=_setup(NET_FILES + ["demand_clean.csv", "calendar.csv", "districts.csv"]), wall=720),
    "H8": dict(title="Vague ask: 'Cut freight cost.'", user=H8_USER, check=h8_check,
               setup=_setup(NET_FILES + ["h3_depot_demand.csv", "depots.csv"]), wall=360),
    "H9": dict(title="Prompt contradicts data file (P5 capacity)", user=H9_USER, check=h9_check,
               setup=_setup(NET_FILES + ["h3_depot_demand.csv"]), wall=420),
}

# ================================================================== E1-E8 general Excel round (added after the steering request)
from excel_tests import E_TESTS  # noqa: E402
TESTS.update(E_TESTS)
