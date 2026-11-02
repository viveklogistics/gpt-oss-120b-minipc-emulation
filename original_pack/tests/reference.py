"""Compute the ground truth for T2-T5 from tests/data/* with our own code (no LLM). Writes data/reference.json.
Run on the same machine/env as the checkers:  python reference.py"""
import json, itertools, warnings
from pathlib import Path
import numpy as np, pandas as pd

D = Path(__file__).resolve().parent / "data"
warnings.filterwarnings("ignore")

def t2():
    import statsmodels.api as sm
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    df = pd.read_csv(D / "t2_dispatch.csv")
    y = df.trucks.astype(float).values; n = len(y); tr, te = slice(0, n - 12), slice(n - 12, n)
    ex = df[["new_unit"]].astype(float).values
    m = SARIMAX(y[tr], exog=ex[tr], order=(1, 1, 1), seasonal_order=(0, 1, 1, 12)).fit(disp=False)
    f_s = m.forecast(12, exog=ex[te])
    month = pd.PeriodIndex(df.month, freq="M").month
    X = pd.get_dummies(month, prefix="m", drop_first=True).astype(float)
    X.insert(0, "new_unit", df.new_unit.astype(float)); X.insert(0, "t", np.arange(n, dtype=float))
    X = sm.add_constant(X)
    g = sm.GLM(y[tr], X.iloc[tr], family=sm.families.Poisson()).fit()
    f_p = g.predict(X.iloc[te])
    f_b = 0.5 * np.asarray(f_s) + 0.5 * np.asarray(f_p)
    mape = lambda f: float(np.mean(np.abs(y[te] - f) / y[te]) * 100)
    return {"mape_sarimax": round(mape(np.asarray(f_s)), 3), "mape_poisson": round(mape(np.asarray(f_p)), 3),
            "mape_blend": round(mape(f_b), 3), "forecast_blend": [round(v, 1) for v in f_b],
            "actual_test": y[te].tolist()}

def t3_cost(assign, inv, rules):
    """assign: {invoice: truck_label}. Returns (feasible, cost, problems)."""
    probs = []; trucks = {}
    if set(assign) != set(inv.invoice):
        probs.append(f"invoices missing/extra: {sorted(set(inv.invoice) ^ set(assign))}")
    for i, k in assign.items(): trucks.setdefault(str(k), []).append(i)
    row = inv.set_index("invoice"); cost = 0
    for k, lst in trucks.items():
        lst = [i for i in lst if i in row.index]
        if not lst: continue
        w = row.loc[lst, "tonnes"].sum(); ds = set(row.loc[lst, "district"]); ps = set(row.loc[lst, "product"])
        if w > rules["truck_capacity_t"]: probs.append(f"truck {k} {w} t > capacity")
        if len(ps) > 1: probs.append(f"truck {k} mixes bag and bulk")
        if len(ds) > rules["max_districts_per_truck"]: probs.append(f"truck {k} serves {len(ds)} districts")
        for a, b in rules["incompatible_pairs"]:
            if a in lst and b in lst: probs.append(f"truck {k} has incompatible {a},{b}")
        cost += rules["truck_fixed_cost_rs"] + rules["drop_cost_rs_per_district"] * len(ds)
    return (not probs), cost, probs

def t3():
    import pulp
    inv = pd.read_csv(D / "t3_invoices.csv"); R = json.load(open(D / "t3_rules.json"))
    I = list(inv.invoice); K = range(R["max_trucks"]); Ds = sorted(inv.district.unique())
    w = dict(zip(inv.invoice, inv.tonnes)); dist = dict(zip(inv.invoice, inv.district)); prod = dict(zip(inv.invoice, inv["product"]))
    p = pulp.LpProblem("club", pulp.LpMinimize)
    V = lambda n: pulp.LpVariable(n, cat="Binary")
    x = {i: {k: V(f"x_{i}_{k}") for k in K} for i in I}; u = {k: V(f"u_{k}") for k in K}
    z = {d: {k: V(f"z_{d}_{k}") for k in K} for d in Ds}; b = {k: V(f"bulk_{k}") for k in K}
    p += pulp.lpSum(R["truck_fixed_cost_rs"] * u[k] + R["drop_cost_rs_per_district"] * pulp.lpSum(z[d][k] for d in Ds) for k in K)
    for i in I: p += pulp.lpSum(x[i][k] for k in K) == 1
    for k in K:
        p += pulp.lpSum(w[i] * x[i][k] for i in I) <= R["truck_capacity_t"] * u[k]
        p += pulp.lpSum(z[d][k] for d in Ds) <= R["max_districts_per_truck"]
        for i in I:
            p += x[i][k] <= z[dist[i]][k]
            p += (x[i][k] <= b[k]) if prod[i] == "bulk" else (x[i][k] <= 1 - b[k])
        for a, c in R["incompatible_pairs"]: p += x[a][k] + x[c][k] <= 1
        if k > 0: p += u[k] <= u[k - 1]
    p.solve(pulp.HiGHS(msg=False))
    assert pulp.LpStatus[p.status] == "Optimal", pulp.LpStatus[p.status]
    assign = {i: next(k for k in K if x[i][k].value() > 0.5) for i in I}
    ok, c, probs = t3_cost(assign, inv, R); assert ok, probs
    return {"optimal_cost_rs": c, "trucks_used": len(set(assign.values())), "assignment": assign,
            "lower_bound_trucks_by_weight": int(np.ceil(inv.tonnes.sum() / R["truck_capacity_t"]))}

def t4():
    import cvxpy as cp
    q = json.load(open(D / "t4_qp.json")); Q, c, A, b = (np.array(q[k], float) for k in ("Q", "c", "A", "b"))
    x = cp.Variable(3); cons = [A @ x <= b, x >= 0]
    pr = cp.Problem(cp.Minimize(0.5 * cp.quad_form(x, Q) + c @ x), cons); pr.solve(solver=cp.CLARABEL, tol_gap_abs=1e-10, tol_gap_rel=1e-10, tol_feas=1e-10)
    xs, lam, mu = x.value, cons[0].dual_value, cons[1].dual_value
    stat = Q @ xs + c + A.T @ lam - mu
    res = max(np.abs(stat).max(), np.abs(lam * (A @ xs - b)).max(), np.abs(mu * xs).max(),
              max(0, (A @ xs - b).max()), max(0, -xs.min()))
    return {"x": np.round(xs, 6).tolist(), "lambda_Ax_le_b": np.round(lam, 6).tolist(), "mu_x_ge_0": np.round(mu, 6).tolist(),
            "objective": round(float(pr.value), 6), "kkt_max_residual": float(res),
            "active_constraints": [i for i in range(3) if abs(A[i] @ xs - b[i]) < 1e-6],
            "active_bounds": [j for j in range(3) if abs(xs[j]) < 1e-6]}

def _t5_solve(cap, dem, C):
    from scipy.optimize import linprog
    P, Dn = C.shape
    A_ub = np.zeros((P, P * Dn)); A_eq = np.zeros((Dn, P * Dn))
    for i in range(P): A_ub[i, i * Dn:(i + 1) * Dn] = 1
    for j in range(Dn): A_eq[j, j::Dn] = 1
    r = linprog(C.ravel(), A_ub=A_ub, b_ub=cap, A_eq=A_eq, b_eq=dem, method="highs")
    assert r.status == 0
    return r

def t5():
    T = json.load(open(D / "t5_transport.json")); P = list(T["plants_capacity_t"]); Dn = list(T["districts_demand_t"])
    cap = np.array(list(T["plants_capacity_t"].values()), float); dem = np.array(list(T["districts_demand_t"].values()), float)
    C = np.array(T["cost_rs_per_t"], float); r = _t5_solve(cap, dem, C)
    # Marginal cost of +1 t demand at each district (Rs/t, >0 = cost rises); saving per +1 t capacity at each plant (>=0)
    d_dem = r.eqlin.marginals; d_cap = -r.ineqlin.marginals
    # finite-difference cross-check (both directions) so the reference duals are known to be unique
    fd_dem = [(_t5_solve(cap, dem + e, C).fun - _t5_solve(cap, dem - e, C).fun) / 2 for e in np.eye(len(dem)) * 100]
    fd_dem = [v / 100 for v in fd_dem]
    fd_cap = [-(_t5_solve(cap + e, dem, C).fun - _t5_solve(cap - e, dem, C).fun) / 200 for e in np.eye(len(cap)) * 100]
    assert np.allclose(fd_dem, d_dem, atol=1e-6) and np.allclose(fd_cap, d_cap, atol=1e-6), (fd_dem, d_dem, fd_cap, d_cap)
    # what-if: binding plant with the largest saving gets +2000 t
    k = int(np.argmax(d_cap)); cap2 = cap.copy(); cap2[k] += 2000; r2 = _t5_solve(cap2, dem, C)
    flows = {f"{P[i]}->{Dn[j]}": round(float(v), 3) for (i, j), v in np.ndenumerate(r.x.reshape(C.shape)) if v > 1e-6}
    return {"optimal_cost_rs": round(float(r.fun), 2), "flows_t": flows,
            "district_marginal_cost_rs_per_t": dict(zip(Dn, np.round(d_dem, 4).tolist())),
            "plant_capacity_saving_rs_per_t": dict(zip(P, np.round(d_cap, 4).tolist())),
            "whatif_plant": P[k], "whatif_extra_t": 2000, "whatif_new_cost_rs": round(float(r2.fun), 2),
            "whatif_saving_rs": round(float(r.fun - r2.fun), 2)}

if __name__ == "__main__":
    ref = {"T2": t2(), "T3": t3(), "T4": t4(), "T5": t5()}
    json.dump(ref, open(D / "reference.json", "w"), indent=1)
    print(json.dumps(ref, indent=1))
