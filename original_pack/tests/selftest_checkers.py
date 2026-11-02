"""Offline check that each checker gives pass for the reference answer and fail for a wrong one (no LLM needed)."""
import json
from pathlib import Path
from tests import TESTS, REF
R = REF
def _flat(a):
    if isinstance(a, dict): return " ".join(_flat(v) for v in a.values())
    if isinstance(a, list): return " ".join(_flat(v) for v in a)
    return str(a)
def log(answer, final="stationarity primal feasibility dual feasibility complementary slackness", py=True, printed=True):
    res = json.dumps({"exit_code": 0, "stdout": _flat(answer) if printed else "done", "stderr": ""})
    return {"answer": answer, "final_text": final, "tool_calls": ([{"tool": "python_exec", "error": None, "valid_json": True, "result": res}] if py else [])}
t3 = R["T3"]; trucks = {}
for inv, k in t3["assignment"].items(): trucks.setdefault(k, []).append(inv)
good = {
 "T2": {k: R["T2"][k] for k in ("mape_sarimax", "mape_poisson", "mape_blend")},
 "T3": {"total_cost_rs": t3["optimal_cost_rs"], "trucks": list(trucks.values())},
 "T4": {"x": R["T4"]["x"], "lambda": R["T4"]["lambda_Ax_le_b"], "mu": R["T4"]["mu_x_ge_0"], "objective": R["T4"]["objective"],
        "kkt_max_residual": 1e-9, "active_constraints": R["T4"]["active_constraints"], "active_bounds": R["T4"]["active_bounds"],
        "kkt_conditions": "stationarity, primal feasibility, dual feasibility, complementary slackness"},
 "T5": {"total_cost_rs": R["T5"]["optimal_cost_rs"], "district_marginal_cost_rs_per_t": R["T5"]["district_marginal_cost_rs_per_t"],
        "plant_capacity_saving_rs_per_t": {k.split("_")[0]: v for k, v in R["T5"]["plant_capacity_saving_rs_per_t"].items()},
        "whatif_new_cost_rs": R["T5"]["whatif_new_cost_rs"]},
}
bad = {"T2": {"mape_sarimax": 9, "mape_poisson": 9, "mape_blend": 9}, "T3": {"total_cost_rs": 1, "trucks": [["INV05", "INV10"]]},
       "T4": {"x": [1, 1, 1]}, "T5": {"total_cost_rs": 1}}
ok = True
for t in good:
    vg, dg = TESTS[t]["check"](log(good[t]), Path("."))
    vb, _ = TESTS[t]["check"](log(bad[t]), Path("."))
    vn, _ = TESTS[t]["check"](log(good[t], py=False), Path("."))
    vu, _ = TESTS[t]["check"](log(good[t], printed=False), Path("."))
    print(t, "reference->", vg, "| wrong->", vb, "| no python->", vn, "| right numbers never printed by code->", vu)
    ok &= vg == "pass" and vb == "fail" and vn == "fail" and vu != "pass"
    if vg != "pass": print(json.dumps(dg, default=str)[:800])
print("ALL CHECKERS OK" if ok else "CHECKER PROBLEM")
