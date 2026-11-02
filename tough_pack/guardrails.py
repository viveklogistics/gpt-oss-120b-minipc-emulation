"""Guarded mode for the tough pack: three extra tools plus extra system-prompt rules.
  data_quality          -> reports duplicates, unit-suspect rows, statistical outliers and missing periods as FLAGS
                           (it never edits or deletes anything)
  check_prompt_vs_data  -> compares numeric facts stated in the task prompt with the data files, reports mismatches
  forecast_blend        -> the tested 50/50 SARIMAX + Poisson-regression blend with WLS (MinT-diagonal) reconciliation
                           bottom -> parent -> total, plus an honest holdout MAPE
Baseline mode does not import any of this; the baseline tests, checkers and data are unchanged.
All data the tools see is ILLUSTRATIVE SYNTHETIC DATA."""
import json, math, re, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd

GUARD_RULES = """
GUARDRAILS (mandatory in this session):
1. DATA QUALITY FIRST. Before any analysis, call data_quality on the main input data file(s) you will use (at least the
   largest one). It only reports flags; it never deletes anything. Decide yourself what to fix. Remove exact duplicates
   and convert units when the evidence is clear. Drop or replace a row as an OUTLIER only with a stated, specific
   justification (for example a value ~100x the group's typical level that no unit conversion explains); never drop rows
   just because a generic rule such as 3-sigma flags them. Report what you flagged, what you changed and why.
2. PROMPT VS DATA. At the start, call check_prompt_vs_data. If it reports any mismatch between a number stated in the
   task and the data files, you MUST tell the user explicitly (name both values and the file) in your answer and in the
   notes/explanation you submit, and say which value you used and why.
3. CLARIFY VAGUE GOALS. If the goal lacks a target, a constraint or a scope (what, how much, which part, which period),
   do NOT start solving silently: either ask the user a short clarifying question and stop, or write your explicit
   assumptions (as a numbered list starting with the word "Assumptions") BEFORE running any solver.
4. FORECASTING. If a task asks for a forecast and does not prescribe one exact method, prefer the forecast_blend tool
   (a tested 50/50 SARIMAX + Poisson blend with WLS reconciliation that also returns the holdout MAPE). If the task
   prescribes an exact method, follow the task instead.
5. Numbers you report must come from tool output (python_exec, data_quality, check_prompt_vs_data or forecast_blend).
"""

def _fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}

GUARD_TOOLS = [
    _fn("data_quality", "Profile a CSV or XLSX file in the working directory and report data-quality FLAGS: exact duplicate "
        "rows, repeated ids, unit-suspect rows (unit column differs from the dominant unit), statistical outliers per group "
        "(ratio to group median, robust z, 3-sigma counts), missing group x month periods, nulls and non-positive values. "
        "Read-only: it never edits or deletes anything. Column arguments are optional (auto-detected).",
        {"path": {"type": "string"}, "sheet": {"type": "string"}, "id_col": {"type": "string"}, "date_col": {"type": "string"},
         "group_col": {"type": "string"}, "value_col": {"type": "string"}, "unit_col": {"type": "string"}}, ["path"]),
    _fn("check_prompt_vs_data", "Compare the numeric facts stated in the task prompt (for example 'X's capacity is 150,000') "
        "with the values in the data files, and report matches and mismatches. Optionally pass extra claims to check.",
        {"claims": {"type": "array", "description": "optional extra claims",
                    "items": {"type": "object", "properties": {"file": {"type": "string"}, "entity": {"type": "string"},
                              "column": {"type": "string"}, "value": {"type": "number"}}}}}, []),
    _fn("forecast_blend", "Tested hierarchical forecaster: per series a 50/50 blend of SARIMAX(1,1,1)(0,1,1,12) and a Poisson "
        "regression (constant, trend, 11 month dummies, calendar flags), for every bottom series, every parent and the total; "
        "then WLS (MinT-diagonal, weights = 1/in-sample residual variance) reconciliation so bottom series add up exactly to "
        "parents and parents to the total. Also backtests the same pipeline on the last holdout_months of history and returns "
        "the bottom-level holdout MAPE. Writes a CSV with columns level, id, month, forecast.",
        {"demand_path": {"type": "string", "description": "long CSV: id, month (YYYY-MM), value"},
         "hierarchy_path": {"type": "string", "description": "CSV mapping each bottom id to its parent"},
         "calendar_path": {"type": "string", "description": "optional CSV month + 0/1 flags (must cover the future months)"},
         "id_col": {"type": "string"}, "parent_col": {"type": "string"}, "month_col": {"type": "string"}, "value_col": {"type": "string"},
         "horizon": {"type": "integer", "description": "months ahead, default 3"},
         "holdout_months": {"type": "integer", "description": "default 3"},
         "out_path": {"type": "string", "description": "default forecast_blend_reconciled.csv"}}, ["demand_path", "hierarchy_path"]),
]

# ------------------------------------------------------------------------------------------------ data_quality
def _read_any(p: Path, sheet=None):
    if p.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(p, sheet_name=sheet or 0)
    return pd.read_csv(p)

def _pick(cols, pats):
    for pat in pats:
        for c in cols:
            if re.search(pat, str(c), re.I): return c
    return None

def data_quality(wd: Path, path, sheet=None, id_col=None, date_col=None, group_col=None, value_col=None, unit_col=None):
    p = (wd / Path(str(path)).name)
    if not p.exists(): return {"error": f"no such file {p.name}"}
    df = _read_any(p, sheet); n = len(df); cols = list(df.columns)
    out = {"file": p.name, "rows": n, "columns": [str(c) for c in cols], "note": "FLAGS ONLY - nothing was modified or deleted"}
    dup = df.duplicated(keep="first")
    out["exact_duplicate_rows"] = {"count": int(dup.sum()), "example_row_numbers": [int(i) + 2 for i in np.where(dup)[0][:8]]}
    id_col = id_col or _pick(cols, [r"(^|_)id$", r"id$"])
    if id_col in cols:
        rep = df[~dup][id_col].duplicated(keep=False)
        out["repeated_ids_not_exact_duplicates"] = {"id_col": id_col, "rows": int(rep.sum()),
                                                    "examples": df[~dup][rep][id_col].astype(str).head(6).tolist()}
    out["nulls_per_column"] = {str(c): int(v) for c, v in df.isna().sum().items() if v}
    unit_col = unit_col or _pick(cols, [r"^uom$", r"unit", r"uom"])
    num = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and c not in (id_col,)]
    value_col = value_col or _pick(num, [r"qty|quantity|tonnes|volume|value|amount|revenue|sales|demand"]) or (num[0] if num else None)
    date_col = date_col or _pick(cols, [r"date", r"^month$", r"period"])
    cand = [c for c in cols if c not in (id_col, unit_col, value_col, date_col) and not pd.api.types.is_numeric_dtype(df[c])
            and 2 <= df[c].nunique() <= max(2, n // 5)]
    group_col = group_col or _pick(cand, [r"district|region|customer|depot|store|sku|product|plant|city"]) or (cand[0] if cand else None)
    out["detected"] = {"id_col": id_col, "date_col": date_col, "group_col": group_col, "value_col": value_col, "unit_col": unit_col}
    base = df[~dup].copy()
    if unit_col in cols:
        vc = base[unit_col].astype(str).str.strip().str.upper().value_counts()
        dom = vc.index[0]; sus = base[unit_col].astype(str).str.strip().str.upper() != dom
        info = {"unit_counts_after_exact_dedup": {k: int(v) for k, v in vc.items()}, "dominant_unit": dom, "rows_not_in_dominant_unit": int(sus.sum())}
        if value_col and sus.any() and group_col:
            med = base[~sus].groupby(group_col)[value_col].median()
            r = (base[sus][value_col] / base[sus][group_col].map(med)).replace([np.inf, -np.inf], np.nan).dropna()
            if len(r): info["their_value_vs_group_median_ratio"] = {"median": round(float(r.median()), 2), "p10": round(float(r.quantile(.1)), 2), "p90": round(float(r.quantile(.9)), 2)}
        out["unit_suspect_rows"] = info
        base = base[~sus]
    if value_col in cols:
        v = pd.to_numeric(base[value_col], errors="coerce")
        out["non_positive_or_non_numeric_values"] = int((~(v > 0)).sum())
        if group_col in cols:
            g = base[group_col]; med = v.groupby(g).transform("median")
            mad = (v - med).abs().groupby(g).transform("median") * 1.4826
            ratio = v / med; rz = (v - med).abs() / mad.replace(0, np.nan)
            mu = v.groupby(g).transform("mean"); sd = v.groupby(g).transform("std")
            three = ((v - mu).abs() > 3 * sd)
            ext = (ratio >= 10) | (ratio <= 0.05)
            top = base.assign(_ratio=ratio, _rz=rz, _k=np.maximum(ratio, 1 / ratio)).loc[ext].sort_values("_k", ascending=False).head(10)
            out["outlier_flags"] = {
                "basis": f"{value_col} within {group_col}, after exact de-dup and excluding unit-suspect rows",
                "extreme_ratio_rows (>=10x or <=0.05x group median)": int(ext.sum()),
                "robust_z_gt_5_rows": int((rz > 5).sum()), "robust_z_gt_3_5_rows": int((rz > 3.5).sum()),
                "three_sigma_rows": int(three.sum()),
                "extreme_examples": [{**{str(k): (v2 if not isinstance(v2, float) else round(v2, 3)) for k, v2 in r.items() if not str(k).startswith("_")},
                                      "ratio_to_group_median": round(float(r["_ratio"]), 2)} for _, r in top.iterrows()],
                "warning": "these are flags, not verdicts; normal variation also produces robust-z and 3-sigma flags"}
    if date_col in cols and group_col in cols:
        per = pd.to_datetime(base[date_col].astype(str), errors="coerce").dt.to_period("M")
        ok = per.notna()
        if ok.any():
            months = pd.period_range(per[ok].min(), per[ok].max(), freq="M")
            present = set(zip(base.loc[ok, group_col], per[ok]))
            groups = sorted(base[group_col].dropna().unique())
            miss = [(gq, str(m)) for gq in groups for m in months if (gq, m) not in present]
            out["missing_group_months"] = {"groups": len(groups), "months": len(months), "range": f"{months[0]}..{months[-1]}",
                                           "count": len(miss), "examples": miss[:12],
                                           "basis": "group x month combinations with no rows at all (after exact de-dup, dominant unit only)"}
            if unit_col in cols:   # also with all units, so the count does not depend on the unit filter
                per_all = pd.to_datetime(df[~dup][date_col].astype(str), errors="coerce").dt.to_period("M")
                pres2 = set(zip(df[~dup][group_col], per_all))
                out["missing_group_months"]["count_including_all_units"] = sum((gq, m) not in pres2 for gq in groups for m in months)
        else: out["missing_group_months"] = "date column could not be parsed"
    return out

# ------------------------------------------------------------------------------------------------ check_prompt_vs_data
_STOP = {"t", "month", "rs", "per", "km", "pct", "id", "the", "of", "a", "in", "is", "to", "and", "s", "x", "there", "for"}
_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "january", "february",
           "march", "april", "june", "july", "august", "september", "october", "november", "december"}
_TOK = re.compile(r"[A-Za-z][A-Za-z0-9_']*|\d[\d,]*(?:\.\d+)?(?:[-/]\d+)*")

def _parts(name): return {w for w in re.split(r"[^a-z0-9]+", str(name).lower()) if w and w not in _STOP}

def _index_files(wd: Path):
    ents, flat = {}, {}
    for f in sorted(wd.iterdir()):
        if not f.is_file() or f.name.startswith("cell_") or f.name in ("transcript.json", "check.json"): continue
        try:
            if f.suffix.lower() == ".json":
                j = json.loads(f.read_text())
                if isinstance(j, dict):
                    for k, v in j.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool): flat[(f.name, k)] = float(v)
                continue
            if f.suffix.lower() not in (".csv", ".xlsx") or f.stat().st_size > 20e6: continue
            df = _read_any(f)
        except Exception: continue
        numc = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        for c in df.columns:
            if pd.api.types.is_numeric_dtype(df[c]): continue
            sc = df[c].astype(str); uniq = ~sc.duplicated(keep=False)
            if uniq.sum() > 2000 or not numc: continue      # transaction ids etc.: not entities the prompt talks about
            for e, (_, row) in zip(sc[uniq], df[uniq].iterrows()):
                if len(e) >= 2 and re.search(r"[A-Za-z]", e) and not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?.*", e):
                    ents.setdefault(e.lower(), []).append((f.name, {str(k): float(row[k]) for k in numc if pd.notna(row[k])}))
    return ents, flat

def check_prompt_vs_data(wd: Path, prompt: str, claims=None):
    ents, flat = _index_files(wd); results = []
    for sent in re.split(r"(?<=[.;:\n])\s+", prompt):
        toks = [(m.group(0), m.start()) for m in _TOK.finditer(sent)]
        words = [re.sub(r"'s$", "", t).lower() for t, _ in toks]
        for i, (t, pos) in enumerate(toks):
            if not t[0].isdigit() or re.search(r"[-/]", t): continue
            if re.search(r"[<>=+*x(]\s*$", sent[:pos]): continue      # bounds / formula constants, not stated facts
            prev, nxt = (words[i - 1] if i else ""), (words[i + 1] if i + 1 < len(words) else "")
            if prev in _MONTHS or nxt in _MONTHS: continue
            try: val = float(t.replace(",", ""))
            except ValueError: continue
            window = set().union(*[_parts(w) for w in words[max(0, i - 8):i]]) if i else set()
            ent = next((words[j] for j in range(i - 1, -1, -1) if words[j] in ents), None)
            cands = []
            if ent:
                for fname, row in ents[ent]:
                    for col, fv in row.items():
                        ov = len(_parts(col) & window)
                        if ov: cands.append((ov, fname, col, fv))
            for (fname, key), fv in flat.items():
                ov = len(_parts(key) & window)
                if ov >= 2 or key.lower() in sent.lower(): cands.append((ov + 0.5, fname, key, fv))
            if not cands: continue
            best = max(c[0] for c in cands); top = [c for c in cands if c[0] == best]
            if len({(c[1], c[2]) for c in top}) > 1:
                if not ent: continue
                results.append({"prompt_text": sent.strip()[:200], "prompt_value": val, "status": "ambiguous",
                                "candidates": [f"{c[1]}:{ent or ''}.{c[2]}={c[3]}" for c in top[:4]]}); continue
            _, fname, col, fv = top[0]
            st = "match" if abs(fv - val) <= max(1e-9, 0.005 * abs(fv)) else "MISMATCH"
            results.append({"prompt_text": sent.strip()[:200], "entity": ent, "prompt_value": val, "file": fname, "column": col,
                            "file_value": fv, "status": st})
    for c in claims or []:
        try:
            e = str(c.get("entity", "")).lower(); col = c.get("column"); val = float(c.get("value"))
            hits = [(f, row[col]) for f, row in ents.get(e, []) if col in row and (not c.get("file") or f == c.get("file"))]
            hits += [(f, v) for (f, k), v in flat.items() if k == col and not e]
            if not hits: results.append({"claim": c, "status": "not found in data"}); continue
            f, fv = hits[0]
            results.append({"claim": c, "file": f, "file_value": fv, "status": "match" if abs(fv - val) <= 0.005 * abs(fv) else "MISMATCH"})
        except Exception as ex: results.append({"claim": c, "status": f"could not check: {ex}"})
    mism = [r for r in results if r["status"] == "MISMATCH"]
    return {"checked": len(results), "mismatches": len(mism), "results": results[:20],
            "summary": ("MISMATCH FOUND - tell the user which value differs and which one you use" if mism else
                        "no mismatch found" if results else "no numeric facts about specific data rows were found in the prompt")}

# ------------------------------------------------------------------------------------------------ forecast_blend
def _design(months, cal, t0):
    P = pd.PeriodIndex(months, freq="M"); t = np.array([(p - t0).n for p in P], float)
    X = [np.ones(len(P)), t] + [(P.month == k).astype(float) for k in range(2, 13)]
    names = ["const", "t"] + [f"m{k}" for k in range(2, 13)]
    ex = None
    if cal is not None:
        ex = cal.reindex([str(p) for p in P]).fillna(0).values.astype(float)
        X += [ex[:, j] for j in range(ex.shape[1])]; names += list(cal.columns)
    return np.column_stack(X), ex, names

def _fit_one(args):
    y, Xf, Xo, exf, exo = args
    import statsmodels.api as sm
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    warnings.filterwarnings("ignore")
    try:
        from threadpoolctl import threadpool_limits; threadpool_limits(1)   # one BLAS thread per worker, no oversubscription
    except Exception: pass
    h = Xo.shape[0]; out = {"sarimax_ok": True}
    keep = Xf.std(0) > 0; keep[0] = True
    g = sm.GLM(y, Xf[:, keep], family=sm.families.Poisson()).fit()
    fp = g.predict(Xo[:, keep]); fitp = g.fittedvalues
    try:
        exk = None
        if exf is not None:
            kk = exf.std(0) > 0
            if kk.any(): exk = (exf[:, kk], exo[:, kk])
        m = SARIMAX(y, exog=exk[0] if exk else None, order=(1, 1, 1), seasonal_order=(0, 1, 1, 12)).fit(disp=False)
        fs = np.asarray(m.forecast(h, exog=exk[1] if exk else None)); fits = np.asarray(m.fittedvalues)
        if not np.all(np.isfinite(fs)): raise ValueError("non-finite SARIMAX forecast")
    except Exception:
        out["sarimax_ok"] = False; fs, fits = fp, fitp
    fb = 0.5 * fs + 0.5 * fp; fit_b = 0.5 * fits + 0.5 * fitp
    res = (y - fit_b)[13:] if len(y) > 20 else (y - fit_b)
    out.update(fc=fb, var=float(np.mean(res ** 2)) or 1e-9)
    return out

def _pipeline(piv, parent, cal, fit_months, out_months, t0):
    bottoms = list(piv.index); parents = sorted(parent.loc[bottoms].unique())
    series = [("total", "TOTAL", piv[fit_months].sum().values)]
    series += [("parent", p, piv.loc[parent.loc[bottoms] == p, fit_months].sum().values) for p in parents]
    series += [("bottom", b, piv.loc[b, fit_months].values) for b in bottoms]
    Xf, exf, _ = _design(fit_months, cal, t0); Xo, exo, _ = _design(out_months, cal, t0)
    jobs = [(np.asarray(s[2], float), Xf, Xo, exf, exo) for s in series]
    try:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(max(1, min(16, mp.cpu_count()))) as pool: res = pool.map(_fit_one, jobs, chunksize=8)
    except Exception:
        res = [_fit_one(j) for j in jobs]
    nb = len(bottoms)
    S = np.vstack([np.ones(nb)] + [(parent.loc[bottoms] == p).values.astype(float) for p in parents] + [np.eye(nb)])
    Y = np.vstack([r["fc"] for r in res]); Wi = np.diag(1 / np.array([r["var"] for r in res]))
    rec = S @ np.linalg.solve(S.T @ Wi @ S, S.T @ Wi @ Y)
    ids = ["TOTAL"] + parents + bottoms; lv = ["total"] + ["parent"] * len(parents) + ["bottom"] * nb
    return rec, Y, ids, lv, sum(not r["sarimax_ok"] for r in res)

def forecast_blend(wd: Path, demand_path, hierarchy_path, calendar_path=None, id_col=None, parent_col=None, month_col=None,
                   value_col=None, horizon=3, holdout_months=3, out_path="forecast_blend_reconciled.csv"):
    t_start = time.time()
    dem = pd.read_csv(wd / Path(demand_path).name); hie = pd.read_csv(wd / Path(hierarchy_path).name)
    month_col = month_col or _pick(dem.columns, [r"month", r"period", r"date"])
    id_col = id_col or next((c for c in dem.columns if c in hie.columns and c != month_col), dem.columns[0])
    value_col = value_col or _pick([c for c in dem.columns if pd.api.types.is_numeric_dtype(dem[c])], [r"tonnes|qty|value|demand|sales"])
    parent_col = parent_col or _pick(hie.columns, [r"home_plant|parent|plant|region"])
    parent = hie.set_index(id_col)[parent_col]
    dem[month_col] = dem[month_col].astype(str).str[:7]
    piv = dem.pivot_table(index=id_col, columns=month_col, values=value_col, aggfunc="sum").sort_index()
    if piv.isna().any().any(): return {"error": f"demand has {int(piv.isna().sum().sum())} missing id-months; clean/impute first"}
    months = sorted(piv.columns); t0 = pd.Period(months[0], freq="M")
    fut = [str(pd.Period(months[-1], freq="M") + k) for k in range(1, int(horizon) + 1)]
    cal = None
    if calendar_path:
        c = pd.read_csv(wd / Path(calendar_path).name); mc = _pick(c.columns, [r"month", r"period", r"date"])
        c[mc] = c[mc].astype(str).str[:7]; cal = c.set_index(mc).select_dtypes("number")
        missing_fut = [m for m in fut if m not in cal.index]
        if missing_fut: return {"error": f"calendar does not cover future months {missing_fut}"}
    H = int(holdout_months)
    rec_h, base_h, ids, lv, fb_h = _pipeline(piv, parent, cal, months[:-H], months[-H:], t0)
    nb = len(piv); act = piv[months[-H:]].values
    mape_rec = float(np.mean(np.abs(act - rec_h[-nb:]) / act) * 100); mape_base = float(np.mean(np.abs(act - base_h[-nb:]) / act) * 100)
    rec, base, ids, lv, fb = _pipeline(piv, parent, cal, months, fut, t0)
    lvl = {"total": "total", "parent": parent_col if parent_col != "home_plant" else "plant", "bottom": id_col}
    rows = [dict(level=lvl[lv[i]], id=ids[i], month=m, forecast=float(rec[i, j])) for i in range(len(ids)) for j, m in enumerate(fut)]
    pd.DataFrame(rows).to_csv(wd / Path(out_path).name, index=False)
    npar = len(ids) - nb - 1
    coh_p = float(max(abs(rec[1 + k] - rec[1 + npar:][(parent.loc[ids[1 + npar:]] == ids[1 + k]).values].sum(0)).max() for k in range(npar)))
    coh_t = float(np.abs(rec[0] - rec[1:1 + npar].sum(0)).max())
    return {"method": "per series 0.5*SARIMAX(1,1,1)(0,1,1,12)+exog flags + 0.5*Poisson GLM(const, t, 11 month dummies, flags); "
                      "WLS reconciliation with weights 1/in-sample residual variance (MinT-diagonal)",
            "levels": {"total": 1, lvl["parent"]: npar, lvl["bottom"]: nb}, "fit_months": f"{months[0]}..{months[-1]}", "forecast_months": fut,
            "holdout": {"fit_months": f"{months[0]}..{months[-H - 1]}", "test_months": months[-H:],
                        "bottom_level_mape_pct_reconciled": round(mape_rec, 3), "bottom_level_mape_pct_unreconciled": round(mape_base, 3),
                        "sarimax_fallbacks_to_poisson": fb_h},
            "total_forecast": [round(float(x), 1) for x in rec[0]],
            "parent_forecasts": {ids[1 + k]: [round(float(x), 1) for x in rec[1 + k]] for k in range(npar)},
            "max_coherence_error": {"bottom_vs_parent": round(coh_p, 6), "parent_vs_total": round(coh_t, 6)},
            "sarimax_fallbacks_to_poisson": fb, "out_file": Path(out_path).name, "rows_written": len(rows),
            "runtime_s": round(time.time() - t_start, 1)}

def make_guard_funcs(wd: Path, prompt: str):
    return {"data_quality": lambda **k: data_quality(wd, **k),
            "check_prompt_vs_data": lambda claims=None, **k: check_prompt_vs_data(wd, prompt, claims),
            "forecast_blend": lambda **k: forecast_blend(wd, **k)}
