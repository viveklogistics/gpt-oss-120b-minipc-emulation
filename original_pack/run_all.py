"""Run the test pack against an OpenAI-compatible llama-server and write scoresheet.xlsx + scoresheet.md.

  python run_all.py --base-url https://<podid>-8000.proxy.runpod.net/v1 --label "gpt-oss-120b A100"
  python run_all.py --base-url http://127.0.0.1:8080/v1 --tests T2,T4 --label "qwen3-4b CPU (harness check)" --no-gmktec

Options: --repeats N (run each test N times), --reasoning-effort low|medium|high (gpt-oss only),
         --terminate-pod POD_ID (terminate the RunPod pod when finished, needs RUNPOD_API_KEY)."""
import argparse, json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path
import requests
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tests"))
from harness import run_agent          # noqa: E402
from tests import TESTS                # noqa: E402

def server_info(base):
    info = {}
    root = base.rstrip("/").removesuffix("/v1")
    for path in ("/v1/models", "/props"):
        try:
            j = requests.get(root + path, timeout=30).json()
            if path == "/v1/models": info["model"] = ",".join(m.get("id", "") for m in j.get("data", []))
            else:
                info["n_ctx"] = (j.get("default_generation_settings") or {}).get("n_ctx")
                info["build"] = j.get("build_info") or j.get("build_number")
        except Exception as e:
            info[path] = f"unavailable: {e}"
    return info

def score(name, T, log, wd, a):
    try: verdict, det = T["check"](log, wd)
    except Exception as e: verdict, det = "fail", {"checker_error": f"{type(e).__name__}: {e}"}
    (wd / "check.json").write_text(json.dumps({"verdict": verdict, "details": det}, indent=1, default=str))
    calls = log["tool_calls"]; gen = log["gen_tok_s"]
    return {"test": name, "title": T["title"], "verdict": verdict,
            "result": json.dumps(log.get("answer"), default=str)[:400] if log.get("answer") is not None
                      else (log.get("final_text") or "")[:400],
            "answer_via": log.get("answer_via"), "stop": log.get("stop"),
            "tool_calls": len(calls), "tool_errors": sum(bool(c["error"]) for c in calls),
            "bad_json_calls": sum(not c["valid_json"] for c in calls),
            "tools_used": ", ".join(dict.fromkeys(c["tool"] for c in calls)),
            "wall_s": log["wall_s"], "gen_tokens": int(log["timings"]["predicted_n"]),
            "prompt_tokens": int(log["timings"]["prompt_n"]), "gen_tok_s": gen, "prompt_tok_s": log["prompt_tok_s"],
            "est_gmktec_gen_tok_s (ESTIMATE = gen_tok_s / %g)" % a.gmktec_divisor:
                (None if a.no_gmktec or not gen else round(gen / a.gmktec_divisor, 1)),
            "checker_details": json.dumps(det, default=str)[:1500]}

def rescore(a):
    """Re-run the checkers on saved transcripts (no model calls) and rewrite the scoresheet."""
    out = Path(a.rescore); rows = []
    meta = json.loads((out / "run_meta.json").read_text()) if (out / "run_meta.json").exists() else {}
    for wd in sorted(p for p in out.iterdir() if (p / "transcript.json").exists()):
        log = json.loads((wd / "transcript.json").read_text())["log"]
        rows.append(score(wd.name, TESTS[wd.name.split("_")[0]], log, wd, a))
    write_sheets(rows, out, a, meta.get("info", {}), meta.get("elapsed", sum(r["wall_s"] for r in rows)))
    for r in rows: print(r["test"], r["verdict"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1"))
    ap.add_argument("--model", default=os.getenv("LLM_MODEL", "local"))
    ap.add_argument("--tests", default="T2,T3,T4,T5")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--label", default="")
    ap.add_argument("--reasoning-effort", default=os.getenv("REASONING_EFFORT", "medium"))
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--max-tokens", type=int, default=8192, help="max tokens per model turn")
    ap.add_argument("--wall-limit", type=int, default=1200, help="seconds per test before it is cut off")
    ap.add_argument("--gmktec-divisor", type=float, default=7.0)
    ap.add_argument("--no-gmktec", action="store_true", help="leave the GMKtec estimate blank (e.g. CPU runs)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--terminate-pod", default=None)
    ap.add_argument("--rescore", default=None, help="results folder: re-check saved transcripts, no model calls")
    a = ap.parse_args()
    if a.rescore: return rescore(a)

    out = Path(a.out or HERE / "results" / datetime.now().strftime("run_%Y%m%d_%H%M%S")); out.mkdir(parents=True, exist_ok=True)
    info = server_info(a.base_url); print("server:", info, flush=True)
    rows, t_all = [], time.time()
    try:
        for tid in [t.strip() for t in a.tests.split(",") if t.strip()]:
            T = TESTS[tid]
            for rep in range(1, a.repeats + 1):
                name = tid if a.repeats == 1 else f"{tid}_r{rep}"
                wd = out / name; wd.mkdir(exist_ok=True)
                print(f"== {name}: {T['title']}", flush=True)
                tools, funcs = T["setup"](wd)
                log = run_agent(T["system"], T["user"], tools, funcs, wd, a.base_url, a.model, a.max_steps,
                                a.wall_limit, a.max_tokens, a.reasoning_effort or None)
                row = score(name, T, log, wd, a)
                rows.append(row)
                print(f"   -> {row['verdict']}  calls={row['tool_calls']} wall={row['wall_s']}s gen={row['gen_tok_s']} tok/s", flush=True)
                write_sheets(rows, out, a, info, time.time() - t_all)
                (out / "run_meta.json").write_text(json.dumps({"info": info, "elapsed": time.time() - t_all, "args": vars(a)}))   # rewrite after every test (crash-safe)
    finally:
        if a.terminate_pod:
            print("terminating pod", a.terminate_pod, flush=True)
            subprocess.run([sys.executable, str(HERE / "runpod_ctl.py"), "terminate", a.terminate_pod])
    print("scoresheet:", out / "scoresheet.md")

def write_sheets(rows, out, a, info, elapsed):
    df = pd.DataFrame(rows)
    tot = {"pass": (df.verdict == "pass").sum(), "partial": (df.verdict == "partial").sum(), "fail": (df.verdict == "fail").sum()}
    pn = df.gen_tokens.sum(); 
    meta = {"label": a.label, "base_url": a.base_url, "server": json.dumps(info), "reasoning_effort": a.reasoning_effort,
            "run_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"), "total_wall_min": round(elapsed / 60, 1),
            "totals": f"{tot['pass']} pass / {tot['partial']} partial / {tot['fail']} fail",
            "gmktec_note": ("not estimated" if a.no_gmktec else
                            f"GMKtec EVO-X2 tok/s is an ESTIMATE = measured A100 tok/s / {a.gmktec_divisor:g} "
                            "(memory bandwidth ratio, not measured on the device)"),
            "data_note": "All data is ILLUSTRATIVE SYNTHETIC DATA (fictional places and numbers)."}
    with pd.ExcelWriter(out / "scoresheet.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="scoresheet", index=False)
        pd.DataFrame(list(meta.items()), columns=["field", "value"]).to_excel(xw, sheet_name="run_info", index=False)
    cols = ["test", "verdict", "tool_calls", "tool_errors", "bad_json_calls", "wall_s", "gen_tok_s", "prompt_tok_s",
            [c for c in df.columns if c.startswith("est_gmktec")][0], "stop", "result"]
    md = [f"# Scoresheet: {a.label}", ""] + [f"- **{k}**: {v}" for k, v in meta.items()] + ["", "| " + " | ".join(cols) + " |",
          "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        md.append("| " + " | ".join(str(r[c]).replace("|", "/").replace("\n", " ")[:160] for c in cols) + " |")
    md += ["", "## Checker details", ""] + [f"- **{r.test}** ({r.verdict}): `{r.checker_details[:900]}`" for _, r in df.iterrows()]
    (out / "scoresheet.md").write_text("\n".join(md) + "\n")

if __name__ == "__main__":
    main()
