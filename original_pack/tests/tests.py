"""Five tests: prompt, tool set and an automatic checker each. Checkers compare against data/reference.json
(computed by reference.py, never by the model) and return (verdict, details) with verdict in pass/partial/fail."""
import importlib.util, json, math, os, re, shutil, sys
from pathlib import Path
import pandas as pd
from harness import PYTHON_TOOL, SUBMIT_TOOL, PY_LIBS, make_python_exec

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
REF = json.load(open(DATA / "reference.json"))

PY_SYSTEM = ("You are a quantitative analyst agent for a logistics team. All data in this task is "
             "ILLUSTRATIVE (synthetic). You have a python_exec tool that runs Python 3 with " + PY_LIBS + ". "
             "Do every calculation by running code with python_exec; never compute numbers in your head or invent them. "
             "If code fails, read the error, fix it and run again. When finished, call submit_answer exactly once with "
             "the JSON keys the task asks for (numbers as plain numbers, not strings), then reply with a 2-4 line summary.")

def _num(v):
    try:
        if isinstance(v, str): v = v.replace(",", "").replace("Rs", "").replace("₹", "").replace("%", "").strip()
        f = float(v); return f if math.isfinite(f) else None
    except Exception: return None

def _get(ans, *names):
    if not isinstance(ans, dict): return None
    low = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in ans.items()}
    for n in names:
        k = re.sub(r"[^a-z0-9]", "", n.lower())
        if k in low: return low[k]
    return None


def _tool_numbers(log):
    """All numbers printed by python_exec (stdout) during the run."""
    nums = []
    for t in log["tool_calls"]:
        if t["tool"] != "python_exec": continue
        try: out = json.loads(t["result"]).get("stdout", "")
        except Exception: out = t.get("result", "")
        nums += [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", out.replace(",", ""))]
    return nums

def _grounded(log, value, rel=0.01, abs_tol=0.011):
    """True if `value` (as submitted) was actually printed by the model's own code: guards against invented numbers."""
    if value is None: return False
    return any(abs(n - value) <= max(abs_tol, rel * abs(value)) for n in _tool_numbers(log))

def _py_used(log): return any(t["tool"] == "python_exec" for t in log["tool_calls"])

# =====================================================================  T2 forecast
T2_USER = """File t2_dispatch.csv has 78 months (2020-01 to 2026-06) of ILLUSTRATIVE monthly truck dispatches:
columns month, trucks (count), new_unit (0/1 step dummy: a new finishing unit from 2024-01).
Backtest a 50/50 blend forecast exactly as specified:
1. Train = first 66 months, test = last 12 months (one forecast origin, 12 steps ahead, no refitting).
2. SARIMAX: statsmodels.tsa.statespace.sarimax.SARIMAX(endog=trucks, exog=new_unit, order=(1,1,1),
   seasonal_order=(0,1,1,12)) with default settings, .fit(disp=False); forecast 12 steps with the test exog.
3. Poisson regression: statsmodels GLM, family Poisson (log link), regressors = constant, t (month index 0..77),
   new_unit, and 11 calendar-month dummies (January is the base). Fit on train, predict the mean for test.
4. Blend = 0.5*SARIMAX + 0.5*Poisson.
5. MAPE (%) on the 12 test months = mean(|actual - forecast| / actual) * 100, for each of the three forecasts.
Call submit_answer with keys: mape_sarimax, mape_poisson, mape_blend (percent, e.g. 3.21), and forecast_blend (list of 12 numbers)."""

def t2_check(log, workdir):
    r = REF["T2"]; a = log.get("answer") or {}
    got = {k: _num(_get(a, k)) for k in ("mape_sarimax", "mape_poisson", "mape_blend")}
    err = {k: (None if got[k] is None else round(abs(got[k] - r[k]), 3)) for k in got}
    det = {"got": got, "reference": {k: r[k] for k in got}, "abs_err_pp": err, "python_used": _py_used(log)}
    det["blend_printed_by_code"] = _grounded(log, got["mape_blend"])
    if not _py_used(log) or not det["blend_printed_by_code"]: return "fail", det
    ok = lambda k, tol: err[k] is not None and err[k] <= tol
    if ok("mape_blend", 0.25) and ok("mape_sarimax", 0.5) and ok("mape_poisson", 0.5): return "pass", det
    if ok("mape_blend", 1.0) or (ok("mape_sarimax", 0.5) and ok("mape_poisson", 0.5)): return "partial", det
    return "fail", det

# =====================================================================  T3 clubbing MILP
T3_USER = """Club 12 invoices onto trucks at minimum cost (ILLUSTRATIVE data). Files: t3_invoices.csv (invoice, district,
tonnes, product = bag|bulk) and t3_rules.json. Rules:
- each invoice goes on exactly one truck (no splitting); truck capacity 30 t; at most 12 trucks available
- bagged and bulk product cannot share a truck
- a truck may serve at most 2 distinct districts
- INV05 and INV10 must not share a truck
- cost of each truck used = Rs 18,000 fixed + Rs 1,500 per distinct district it serves
Formulate this as a mixed-integer program and solve it to proven optimality with the HiGHS solver (highspy, or
pulp with pulp.HiGHS / HiGHS_CMD, or scipy.optimize.milp). Verify your plan against every rule in code.
Call submit_answer with keys: total_cost_rs (number), trucks_used (number), and trucks (a list of lists of invoice ids,
one inner list per truck, e.g. [["INV01","INV02"],["INV03"]])."""

def t3_check(log, workdir):
    sys.path.insert(0, str(HERE)); from reference import t3_cost
    r = REF["T3"]; a = log.get("answer") or {}
    inv = pd.read_csv(DATA / "t3_invoices.csv"); rules = json.load(open(DATA / "t3_rules.json"))
    trucks = _get(a, "trucks", "plan", "assignment"); assign = {}
    try:
        if isinstance(trucks, dict):
            if all(isinstance(v, list) for v in trucks.values()):
                for k, lst in trucks.items():
                    for i in lst: assign[str(i).upper()] = k
            else: assign = {str(k).upper(): v for k, v in trucks.items()}
        elif isinstance(trucks, list):
            for k, lst in enumerate(trucks):
                lst = lst.get("invoices", []) if isinstance(lst, dict) else lst
                for i in lst: assign[str(i).upper()] = k
    except Exception: pass
    feas, cost, probs = t3_cost(assign, inv, rules) if assign else (False, None, ["no plan given"])
    rep = _num(_get(a, "total_cost_rs", "total_cost", "cost"))
    det = {"reported_cost": rep, "recomputed_cost": cost, "feasible": feas, "problems": probs[:5],
           "reference_optimum": r["optimal_cost_rs"], "reference_trucks": r["trucks_used"], "python_used": _py_used(log)}
    det["cost_printed_by_code"] = _grounded(log, rep, rel=0, abs_tol=0.5)
    if not _py_used(log) or not feas: return "fail", det
    if cost == r["optimal_cost_rs"] and not det["cost_printed_by_code"]: return "partial", det
    if cost == r["optimal_cost_rs"] and rep is not None and abs(rep - cost) < 0.5: return "pass", det
    if cost <= 1.05 * r["optimal_cost_rs"]: return "partial", det
    return "fail", det

# =====================================================================  T4 KKT
T4_USER = """File t4_qp.json defines a convex QP: minimise f(x) = 0.5*x'Qx + c'x subject to A x <= b and x >= 0 (x in R^3).
1. Derive the KKT conditions in general form for this problem, using multipliers lambda >= 0 for A x <= b and
   mu >= 0 for x >= 0 (so stationarity is Q x + c + A' lambda - mu = 0). Write each condition out.
2. Solve the QP numerically with cvxpy and read off x*, lambda*, mu* (check the sign convention matches above).
3. Verify numerically that all four KKT conditions hold at the solution and report the largest absolute residual.
4. Say which constraints and which bounds are active.
Call submit_answer with keys: x (list of 3), lambda (list of 3), mu (list of 3), objective (number),
kkt_max_residual (number), active_constraints (list of 0-based row indices of A), active_bounds (list of 0-based indices
of x at 0), kkt_conditions (a short text stating stationarity, primal feasibility, dual feasibility and complementary slackness)."""

def _vec(v):
    try: return [float(z) for z in v]
    except Exception: return None

def t4_check(log, workdir):
    r = REF["T4"]; a = log.get("answer") or {}
    x, lam, mu = _vec(_get(a, "x", "x_star")), _vec(_get(a, "lambda", "lambda_star", "lam")), _vec(_get(a, "mu", "mu_star"))
    close = lambda u, v: u is not None and len(u) == len(v) and max(abs(p - q) for p, q in zip(u, v)) <= 2e-3
    x_ok, lam_ok, mu_ok = close(x, r["x"]), close(lam, r["lambda_Ax_le_b"]), close(mu, r["mu_x_ge_0"])
    obj_ok = (_num(_get(a, "objective")) is not None) and abs(_num(_get(a, "objective")) - r["objective"]) <= 2e-3
    res = _num(_get(a, "kkt_max_residual")); res_ok = res is not None and res < 1e-4
    txt = (str(_get(a, "kkt_conditions") or "") + " " + (log.get("final_text") or "")).lower()
    words = {w: (w in txt) for w in ("stationarity", "primal", "dual", "complementary")}
    act_ok = sorted(_get(a, "active_constraints") or []) == r["active_constraints"] and sorted(_get(a, "active_bounds") or []) == r["active_bounds"]
    det = {"x": x, "lambda": lam, "mu": mu, "x_ok": x_ok, "lambda_ok": lam_ok, "mu_ok": mu_ok, "objective_ok": obj_ok,
           "residual_reported": res, "residual_ok": res_ok, "kkt_terms_present": words, "active_sets_ok": act_ok,
           "reference": {k: r[k] for k in ("x", "lambda_Ax_le_b", "mu_x_ge_0", "objective", "active_constraints", "active_bounds")},
           "python_used": _py_used(log)}
    det["objective_printed_by_code"] = _grounded(log, _num(_get(a, "objective")), rel=1e-3, abs_tol=2e-3)
    if not _py_used(log) or not x_ok or not _grounded(log, x[0], rel=1e-3, abs_tol=2e-3): return "fail", det
    if lam_ok and mu_ok and obj_ok and res_ok and all(words.values()) and act_ok and det["objective_printed_by_code"]: return "pass", det
    return "partial", det

# =====================================================================  T5 transport LP + sensitivity
T5_USER = """File t5_transport.json has an ILLUSTRATIVE transport problem: 4 plants (capacity, t), 6 districts (demand, t)
and a cost matrix in Rs/tonne (rows = plants, columns = districts, same order as in the file).
Step 1: Solve the min-cost LP (every district's demand met exactly, plant shipments <= capacity) with HiGHS
(scipy.optimize.linprog(method="highs") or highspy). Report the optimal cost and the non-zero flows.
Step 2: Sensitivity from the duals: (a) for each district, the marginal cost in Rs/t of ONE extra tonne of demand
(positive = total cost rises); (b) for each plant, the saving in Rs/t from ONE extra tonne of capacity (>= 0, zero if the
plant has spare capacity). Mind the solver's sign conventions.
Step 3: Check one dual by re-solving: increase P1_Ashford capacity by 2,000 t, re-solve and report the new optimal cost.
Say whether it agrees with the dual.
Call submit_answer with keys: total_cost_rs, flows (object "plant->district": tonnes),
district_marginal_cost_rs_per_t (object keyed by district name), plant_capacity_saving_rs_per_t (object keyed by plant
name), whatif_new_cost_rs."""

def _match_dict(got, ref, tol):
    if not isinstance(got, dict): return 0, {}
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    out, n = {}, 0
    for k, v in ref.items():
        cand = [gv for gk, gv in got.items() if norm(gk) == norm(k) or norm(k).startswith(norm(gk)) or norm(gk).startswith(norm(k).split("_")[0])
                or norm(k.split("_")[0]) == norm(gk)]
        g = _num(cand[0]) if cand else None
        good = g is not None and abs(g - v) <= tol; n += good; out[k] = (g, v, good)
    return n, out

def t5_check(log, workdir):
    r = REF["T5"]; a = log.get("answer") or {}
    c = _num(_get(a, "total_cost_rs", "total_cost")); cost_ok = c is not None and abs(c - r["optimal_cost_rs"]) <= 1
    nd, dd = _match_dict(_get(a, "district_marginal_cost_rs_per_t", "district_marginal_cost"), r["district_marginal_cost_rs_per_t"], 0.5)
    npl, pd_ = _match_dict(_get(a, "plant_capacity_saving_rs_per_t", "plant_capacity_saving"), r["plant_capacity_saving_rs_per_t"], 0.5)
    w = _num(_get(a, "whatif_new_cost_rs")); w_ok = w is not None and abs(w - r["whatif_new_cost_rs"]) <= 1
    det = {"total_cost": c, "cost_ok": cost_ok, "district_duals_correct": f"{nd}/6", "plant_duals_correct": f"{npl}/4",
           "whatif_new_cost": w, "whatif_ok": w_ok, "district_detail": dd, "plant_detail": pd_,
           "reference_cost": r["optimal_cost_rs"], "reference_whatif": r["whatif_new_cost_rs"], "python_used": _py_used(log)}
    det["cost_printed_by_code"] = _grounded(log, c, rel=0, abs_tol=1)
    if not _py_used(log) or not cost_ok or not det["cost_printed_by_code"]: return "fail", det
    if nd == 6 and npl == 4 and w_ok: return "pass", det
    return "partial", det

# =====================================================================  registry
def _py_setup(files):
    def setup(workdir):
        for f in files: shutil.copy(DATA / f, workdir / f)
        return [PYTHON_TOOL, SUBMIT_TOOL], {"python_exec": make_python_exec(workdir)}
    return setup

TESTS = {
    "T2": dict(title="ML: 50/50 SARIMAX + Poisson blend, 12-month backtest MAPE", system=PY_SYSTEM, user=T2_USER,
               setup=_py_setup(["t2_dispatch.csv"]), check=t2_check),
    "T3": dict(title="OR: invoice clubbing MILP with HiGHS", system=PY_SYSTEM, user=T3_USER,
               setup=_py_setup(["t3_invoices.csv", "t3_rules.json"]), check=t3_check),
    "T4": dict(title="Maths: KKT conditions of a QP, verified with cvxpy", system=PY_SYSTEM, user=T4_USER,
               setup=_py_setup(["t4_qp.json"]), check=t4_check),
    "T5": dict(title="Multi-step: transport LP 4x6 + dual sensitivity + re-solve check", system=PY_SYSTEM, user=T5_USER,
               setup=_py_setup(["t5_transport.json"]), check=t5_check),
}
