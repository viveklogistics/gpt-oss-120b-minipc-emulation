"""Run the tough pack (H1-H9, ILLUSTRATIVE SYNTHETIC supply-chain data) against an OpenAI-compatible
llama-server and write scoresheet.xlsx + scoresheet.md.
  python tough_pack/run_tough.py --base-url https://<pod>-8000.proxy.runpod.net/v1 --label "gpt-oss-120b" \
      --deadline-min 70 --terminate-pod <POD_ID>
  python tough_pack/run_tough.py --base-url http://127.0.0.1:8765/v1 --label mock      (dry run against mock/mock_server.py)
  python tough_pack/run_tough.py --rescore tough_pack/results/run_x                          (re-check saved transcripts)"""
import argparse, json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path
import pandas as pd
import requests
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("PY_TIMEOUT_S", "240"); os.environ.setdefault("PY_MEM_GB", "4")
from harness_tough import run_agent            # noqa: E402
from tests_tough import TESTS, SYSTEM, REF     # noqa: E402
import harness_tough                             # noqa: E402

def server_info(base):
    info = {}; root = base.rstrip("/").removesuffix("/v1")
    for path in ("/v1/models", "/props"):
        try:
            j = requests.get(root + path, timeout=30).json()
            if path == "/v1/models": info["model"] = ",".join(m.get("id", "") for m in j.get("data", []))
            else: info["n_ctx"] = (j.get("default_generation_settings") or {}).get("n_ctx"); info["build"] = j.get("build_info")
        except Exception as e: info[path] = f"unavailable: {e}"
    return info

def reason(verdict, det):
    """One-line human reason from the checker details (only facts the checker computed)."""
    d = det or {}
    try:
        if "checker_error" in d: return d["checker_error"]
        if "real_date_cells" in d: return f"{d['rows']} rows; correct cells {d['correct']}; real date cells {d['real_date_cells']}"
        if "cells_correct" in d: return f"pivot cells correct {d['cells_correct']}/{d['cells_expected']}, regions sorted={d['regions_sorted']}"
        if "Category" in d and isinstance(d["Category"], dict): return "; ".join(f"{k}: formula rows {d[k].get('formula_rows')}, values ok after recalc {d[k].get('value_matches_after_recalc')}/{d[k].get('rows_expected')}" for k in ("Category", "Price_per_t") if isinstance(d.get(k), dict))
        if "formula_rows" in d: return f"formula rows {d['formula_rows']}, values ok after recalc {d['value_matches_after_recalc']}/{d['rows_expected']}; e.g. {d.get('sample_formula')}"
        if "formula_cells_ok" in d: return f"formula cells ok {d['formula_cells_ok']}/{d['expected']}, values ok {d['value_cells_ok']}/{d['expected']}, two-criteria SUMIFS ok={d['north_ppc_ok']}; e.g. A2..B2 {d.get('sample_B2')}"
        if "rows_written" in d: return f"rows {d['rows_written']}/{d['rows_expected']}, order exact={d['order_exact']}, counts reported and printed by code {d['reported_ok_and_printed']}"
        if "cf_rules" in d: return "; ".join(f"CF rule {r.get('range')} {r.get('type')} {r.get('formula')} red={r.get('red')} covers={r.get('covers_revenue_rows')} logic={r.get('logic_ok')}" for r in d["cf_rules"]) or "no conditional formatting rule"
        if "chart_parts" in d: return f"chart {d.get('chart_type')} parts {len(d['chart_parts'])}, plots Total_Revenue={d.get('plots_TotalRevenue')}, title={d.get('title_found')}, monthly values ok={d.get('monthly_values_ok')}"
        if "error" in d: return str(d["error"])
        if "correct" in d: return f"counts correct {d['correct']}; printed by code {d['printed_by_code']}; clean file ok {d.get('clean_file_ok')}"
        if "future_district_mape_pct" in d: return (f"coherent={d['coherent']}, future district MAPE {d['future_district_mape_pct']}% "
            f"(ref {d['ref_future_mape_pct']}%, pass <= {d['pass_band_pct']}%), holdout reported {d['holdout_reported']} (ref {d['ref_holdout_mape_pct']}), WLS code seen={d['wls_code_seen']}")
        if "gap_to_optimum_pct" in d: return (f"feasible={d['feasible']}, gap to optimum {d['gap_to_optimum_pct']}%, reported vs recomputed "
            f"{d['reported_vs_recomputed_pct']}%, printed by code={d['cost_printed_by_code']}; problems {d['problems'][:2]}")
        if "trucks" in d and "gap_pct" in d: return (f"feasible={d['feasible']}, cost {d['recomputed_cost_rs']} vs optimum {d['reference_optimum_rs']} "
            f"(gap {d['gap_pct']}%), trucks {d['trucks']}; problems {d['problems'][:2]}")
        if "flagged_infeasible" in d: return (f"flagged infeasible={d['flagged_infeasible']}, claims plan={d['claims_plan']}, names intermediate={d['mentions_intermediate']}, "
            f"shortfall {d['ref_shortfall_t']} printed={d['shortfall_printed_by_code']}")
        if "shadow_printed_by_code" in d: return f"ok {d['ok']}; delta printed={d['delta_printed_by_code']}, shadow printed={d['shadow_printed_by_code']}"
        if "err_pct" in d: return f"error % vs reference chain {d['err_pct']}; first stage off: {d['first_stage_off']}"
        if "asked_clarifying_question" in d: return (f"asked question={d['asked_clarifying_question']}, assumptions before solving={d['assumptions_stated_before_solving']}, "
            f"only after={d['assumptions_only_after_solving']}")
        if "flags_mismatch_words" in d: return (f"mismatch wording={d['flags_mismatch_words']}, mentions 118000={d['mentions_file_value_118000']}, "
            f"capacity used (from cost)={d['capacity_used_by_cost']}")
        if "plan" in d or "file" in d: return str(d.get("plan") or d.get("file"))
    except Exception as e: return f"(reason unavailable: {e})"
    return ""

def score(name, T, log, wd):
    try: verdict, det = T["check"](log, wd)
    except Exception as e: verdict, det = "fail", {"checker_error": f"{type(e).__name__}: {e}"}
    (wd / "check.json").write_text(json.dumps({"verdict": verdict, "details": det}, indent=1, default=str))
    calls = log["tool_calls"]
    return {"test": name, "title": T["title"], "verdict": verdict, "reason": reason(verdict, det),
            "answer": json.dumps(log.get("answer"), default=str)[:500] if log.get("answer") is not None else (log.get("final_text") or "")[:500],
            "answer_via": log.get("answer_via"), "stop": log.get("stop"), "steps": len(log.get("turns", [])),
            "tool_calls": len(calls), "python_calls": sum(c["tool"] == "python_exec" for c in calls),
            "tool_errors": sum(bool(c["error"]) for c in calls), "self_corrections": log.get("self_corrections"),
            "bad_json_calls": sum(not c["valid_json"] for c in calls), "tools_used": ", ".join(dict.fromkeys(c["tool"] for c in calls)),
            "guard_calls": sum(c["tool"] in ("data_quality", "check_prompt_vs_data", "forecast_blend") for c in calls),
            "context_trims": log.get("trims"), "max_ctx_tokens": log.get("max_ctx_tokens"),
            "wall_s": log["wall_s"], "gen_tokens": int(log["timings"]["predicted_n"]), "prompt_tokens": int(log["timings"]["prompt_n"]),
            "gen_tok_s": log["gen_tok_s"], "prompt_tok_s": log["prompt_tok_s"], "checker_details": json.dumps(det, default=str)[:3000]}

def dataset_summary():
    D = HERE / "data"; P = pd.read_csv(D / "plants.csv"); C = pd.read_csv(D / "intermediate_units.csv")
    return {"data_note": "ILLUSTRATIVE SYNTHETIC DATA - made-up supply network, no real company data or plant names",
            "seed": REF.get("seed"), "plants": len(P), "intermediate_units": len(C), "depots": len(pd.read_csv(D / "depots.csv")),
            "districts": len(pd.read_csv(D / "districts.csv")), "history_months": pd.read_csv(D / "demand_clean.csv").month.nunique(),
            "h1_raw_invoice_rows": REF["h1"]["raw_rows"], "h4_invoices": len(pd.read_csv(D / "h4_invoices.csv")),
            "excel_round_data": "E1-E8: sales.xlsx 150 orders x 9 cols + Products (5); sales_dups.xlsx 157 rows (7 exact dups); customers.xlsx 40 messy rows - illustrative synthetic"}

def write_sheets(rows, out, a, info, elapsed):
    df = pd.DataFrame(rows); tot = df.verdict.value_counts()
    gen_n = df.gen_tokens.sum(); 
    meta = {"label": a.label, "mode": getattr(a, "mode", "baseline"), "base_url": a.base_url, "server": json.dumps(info), "reasoning_effort": a.reasoning_effort,
            "run_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"), "total_wall_min": round(elapsed / 60, 1),
            "totals": f"{tot.get('pass', 0)} pass / {tot.get('partial', 0)} partial / {tot.get('fail', 0)} fail",
            "settings": f"max_steps {a.max_steps}, max_tokens/turn {a.max_tokens}, ctx {info.get('n_ctx') or 'n/a'}, trims at {harness_tough.TRIM_AT_TOKENS} tokens",
            **dataset_summary()}
    with pd.ExcelWriter(out / "scoresheet.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="scoresheet", index=False)
        pd.DataFrame(list(meta.items()), columns=["field", "value"]).to_excel(xw, sheet_name="run_info", index=False)
    cols = ["test", "verdict", "reason", "tool_calls", "tool_errors", "self_corrections", "steps", "wall_s", "gen_tok_s", "prompt_tok_s", "stop"]
    md = [f"# Tough pack scoresheet: {a.label}", ""] + [f"- **{k}**: {v}" for k, v in meta.items()] + ["", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows(): md.append("| " + " | ".join(str(r[c]).replace("|", "/").replace("\n", " ")[:300] for c in cols) + " |")
    md += ["", "## Answers and checker details", ""]
    for _, r in df.iterrows(): md += [f"### {r.test}: {r.title} ({r.verdict})", f"- answer: `{r.answer[:500]}`", f"- details: `{r.checker_details[:1500]}`", ""]
    (out / "scoresheet.md").write_text("\n".join(md) + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1"))
    ap.add_argument("--model", default=os.getenv("LLM_MODEL", "local"))
    ap.add_argument("--tests", default=",".join(TESTS)); ap.add_argument("--label", default="")
    ap.add_argument("--reasoning-effort", default=os.getenv("REASONING_EFFORT", "medium"))
    ap.add_argument("--max-steps", type=int, default=40); ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--deadline-min", type=float, default=None, help="stop starting/continuing tests after this many minutes")
    ap.add_argument("--mode", choices=["baseline", "guarded"], default="baseline",
                    help="guarded = extra system rules + data_quality / check_prompt_vs_data / forecast_blend tools")
    ap.add_argument("--out", default=None); ap.add_argument("--terminate-pod", default=None); ap.add_argument("--rescore", default=None)
    a = ap.parse_args()
    if a.rescore:
        out = Path(a.rescore); meta = json.loads((out / "run_meta.json").read_text()) if (out / "run_meta.json").exists() else {}
        rows = [score(wd.name, TESTS[wd.name], json.loads((wd / "transcript.json").read_text())["log"], wd)
                for wd in sorted(p for p in out.iterdir() if (p / "transcript.json").exists())]
        write_sheets(rows, out, a, meta.get("info", {}), meta.get("elapsed", 0)); [print(r["test"], r["verdict"], r["reason"]) for r in rows]; return
    out = Path(a.out or HERE / "results" / datetime.now().strftime("run_%Y%m%d_%H%M%S")); out.mkdir(parents=True, exist_ok=True)
    t_all = time.time(); deadline = t_all + a.deadline_min * 60 if a.deadline_min else None; rows = []
    try:
        info = server_info(a.base_url); print("server:", info, flush=True)
        if a.mode == "guarded" and not os.getenv("TRIM_AT_TOKENS") and info.get("n_ctx"):   # guarded: trim only near the real context size
            harness_tough.TRIM_AT_TOKENS = max(20000, int(info["n_ctx"]) - a.max_tokens - 4000)
        print("mode:", a.mode, "| trim at", harness_tough.TRIM_AT_TOKENS, "tokens", flush=True)
        system = SYSTEM
        if a.mode == "guarded":
            from guardrails import GUARD_RULES, GUARD_TOOLS, make_guard_funcs
            system = SYSTEM + GUARD_RULES
        for tid in [t.strip() for t in a.tests.split(",") if t.strip()]:
            if deadline and time.time() > deadline - 60: print("deadline reached, skipping", tid, flush=True); continue
            T = TESTS[tid]; wd = out / tid; wd.mkdir(exist_ok=True); print(f"== {tid}: {T['title']}", flush=True)
            tools, funcs = T["setup"](wd)
            if a.mode == "guarded":
                tools = list(tools) + GUARD_TOOLS; funcs = {**funcs, **make_guard_funcs(wd, T["user"])}
            log = run_agent(system, T["user"], tools, funcs, wd, a.base_url, a.model, a.max_steps, int(T["wall"] * float(os.getenv("WALL_SCALE", "1"))), a.max_tokens,
                            a.reasoning_effort or None, deadline=deadline)
            row = score(tid, T, log, wd); rows.append(row)
            print(f"   -> {row['verdict']}: {row['reason'][:200]} | calls={row['tool_calls']} selfcorr={row['self_corrections']} "
                  f"wall={row['wall_s']}s gen={row['gen_tok_s']} tok/s", flush=True)
            write_sheets(rows, out, a, info, time.time() - t_all)
            (out / "run_meta.json").write_text(json.dumps({"info": info, "elapsed": time.time() - t_all, "args": vars(a)}))
    finally:
        if a.terminate_pod:
            print("terminating pod", a.terminate_pod, flush=True)
            subprocess.run([sys.executable, str(HERE.parent / "pod" / "runpod_ctl.py"), "terminate", a.terminate_pod])
    print("scoresheet:", out / "scoresheet.md")

if __name__ == "__main__":
    main()
