"""Agent loop for the tough pack. Reuses tests/harness.py (streaming chat_turn, sandboxed python_exec, tool schemas)
and adds: file tools (list_files / read_file / write_file / write_excel, confined to the test folder), context
management for the 32k window (older tool outputs and reasoning are trimmed once the prompt grows), and counts of
self-corrections (a failed python_exec followed later by a successful one)."""
import json, os, sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "original_pack" / "tests"))
from harness import chat_turn, make_python_exec, _parse_json_answer, PYTHON_TOOL, SUBMIT_TOOL, PY_LIBS  # noqa: E402
from openai import OpenAI

MAX_TOOL_OUT = 6000
TRIM_AT_TOKENS = int(os.getenv("TRIM_AT_TOKENS", "20000"))   # 32k ctx - 8k max_tokens - margin

def _fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}

FILE_TOOLS = [
    _fn("list_files", "List the files in the working directory with their sizes.", {}, []),
    _fn("read_file", "Read part of a text file in the working directory (CSV, JSON, txt).",
        {"path": {"type": "string"}, "start_line": {"type": "integer", "description": "1-based, default 1"},
         "max_lines": {"type": "integer", "description": "default 40, at most 200"}}, ["path"]),
    _fn("write_file", "Write a text file (for example a CSV or a markdown note) into the working directory.",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _fn("write_excel", "Write rows (a list of objects, one per row) to an .xlsx file in the working directory.",
        {"rows": {"type": "array", "items": {"type": "object"}}, "path": {"type": "string"}}, ["rows"]),
]

def make_file_funcs(workdir: Path):
    wd = workdir.resolve()
    def _p(path):
        p = (wd / Path(str(path)).name).resolve()          # flat folder, no escaping it
        return p
    def list_files():
        return {"files": [{"name": f.name, "bytes": f.stat().st_size} for f in sorted(wd.iterdir())
                          if f.is_file() and not f.name.startswith("cell_") and f.name not in ("transcript.json", "check.json")]}
    def read_file(path, start_line=1, max_lines=40):
        p = _p(path)
        if not p.exists(): return {"error": f"no such file {p.name}"}
        lines = p.read_text(errors="replace").splitlines(); s = max(1, int(start_line)); n = min(int(max_lines), 200)
        return {"path": p.name, "total_lines": len(lines), "lines": "\n".join(lines[s - 1:s - 1 + n])[:MAX_TOOL_OUT]}
    def write_file(path, content):
        p = _p(path); p.write_text(str(content)); return {"path": p.name, "bytes": p.stat().st_size}
    def write_excel(rows, path="result.xlsx"):
        p = _p(path if str(path).endswith(".xlsx") else str(path) + ".xlsx")
        if isinstance(rows, dict): rows = [{"field": k, "value": v} for k, v in rows.items()]
        pd.DataFrame(rows).to_excel(p, index=False); return {"path": p.name, "rows": len(rows)}
    return {"list_files": list_files, "read_file": read_file, "write_file": write_file, "write_excel": write_excel}

def _trim(msgs, keep_last=4):
    """Shrink older tool outputs and drop older reasoning so the next prompt fits in 32k."""
    tool_idx = [i for i, m in enumerate(msgs) if m["role"] == "tool"]
    n = 0
    for i in tool_idx[:-keep_last]:
        c = msgs[i]["content"]
        if len(c) > 600: msgs[i]["content"] = c[:300] + " ...[older output trimmed to save context]... " + c[-200:]; n += 1
    asst = [i for i, m in enumerate(msgs) if m["role"] == "assistant"]
    for i in asst[:-2]:
        if msgs[i].pop("reasoning_content", None): n += 1
    return n

def run_agent(system, user, tools, funcs, outdir: Path, base_url, model="local", max_steps=40, wall_limit_s=900,
              max_tokens=8192, reasoning_effort=None, deadline=None):
    client = OpenAI(base_url=base_url, api_key=os.getenv("LLM_API_KEY", "none"), timeout=float(os.getenv("LLM_TIMEOUT_S", "240")), max_retries=1)  # 240 s max silence between stream chunks (a stalled proxy stream hung H4 once)
    extra = {"chat_template_kwargs": {"reasoning_effort": reasoning_effort}} if reasoning_effort else {}
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    log = {"tool_calls": [], "turns": [], "answer": None, "answer_via": None, "final_text": "", "stop": None, "trims": 0}
    tim = {"prompt_n": 0, "prompt_ms": 0.0, "predicted_n": 0, "predicted_ms": 0.0}
    t_start = time.time(); last_ctx = 0
    for step in range(max_steps):
        if time.time() - t_start > wall_limit_s: log["stop"] = f"wall limit {wall_limit_s}s"; break
        if deadline and time.time() > deadline: log["stop"] = "global run deadline"; break
        if last_ctx > TRIM_AT_TOKENS: log["trims"] += _trim(msgs)
        try:
            r = chat_turn(client, model, msgs, tools, extra, max_tokens)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if "context" in msg.lower() or "exceed" in msg.lower():
                log["trims"] += _trim(msgs, keep_last=2)
                try: r = chat_turn(client, model, msgs, tools, extra, max_tokens)
                except Exception as e2: log["stop"] = f"server error: {type(e2).__name__}: {e2}"[:500]; break
            else:
                log["stop"] = f"server error: {msg}"[:500]; break
        if r["timings"]:
            for k in tim: tim[k] += float(r["timings"].get(k, 0) or 0)
        u = r["usage"] or {}; last_ctx = (u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0)
        log["turns"].append({k: r[k] for k in ("content", "reasoning", "tool_calls", "timings", "usage", "finish_reason", "wall_s")})
        am = {"role": "assistant", "content": r["content"] or ""}
        if r["reasoning"]: am["reasoning_content"] = r["reasoning"]
        if r["tool_calls"]:
            am["tool_calls"] = [{"id": c["id"] or f"call_{step}_{i}", "type": "function",
                                 "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for i, c in enumerate(r["tool_calls"])]
        msgs.append(am)
        if not r["tool_calls"]:
            log["final_text"] = r["content"]
            if log["answer"] is None:
                a = _parse_json_answer(r["content"])
                if a is not None: log["answer"], log["answer_via"] = a, "json_in_text"
            log["stop"] = "final_answer" if r["finish_reason"] != "length" else "max_tokens"; break
        done = False
        for c in am["tool_calls"]:
            name, raw = c["function"]["name"], c["function"]["arguments"]
            rec = {"step": step, "tool": name, "args": raw[:6000], "valid_json": True, "error": None}
            try: args = json.loads(raw or "{}")
            except Exception as e: args, rec["valid_json"] = None, False; out = {"error": f"arguments were not valid JSON: {e}"}
            if args is not None:
                if name == "submit_answer":
                    ans = args.get("answer", args)
                    if isinstance(ans, str):
                        try: ans = json.loads(ans)
                        except Exception: pass
                    log["answer"], log["answer_via"] = ans, "submit_answer"; out = {"ok": True}; done = True
                elif name in funcs:
                    try: out = funcs[name](**args)
                    except Exception as e: out = {"error": f"{type(e).__name__}: {e}"}
                else: out = {"error": f"unknown tool {name}"}
            if isinstance(out, dict) and (out.get("error") or out.get("exit_code") not in (None, 0)):
                rec["error"] = str(out.get("error") or out.get("stderr", ""))[-300:]
            res = json.dumps(out, default=str); rec["result"] = res[:MAX_TOOL_OUT]; log["tool_calls"].append(rec)
            print(f"   [{step}] {name} -> {res[:140]}", file=sys.stderr, flush=True)
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": res[:MAX_TOOL_OUT]})
        if done: log["final_text"] = r["content"]; log["stop"] = "submitted"; break
    else:
        log["stop"] = f"max_steps {max_steps}"
    py = [t for t in log["tool_calls"] if t["tool"] == "python_exec"]
    log["self_corrections"] = sum(1 for i, t in enumerate(py) if t["error"] and any(not u["error"] for u in py[i + 1:]))
    log["python_errors"] = sum(1 for t in py if t["error"])
    log["wall_s"] = round(time.time() - t_start, 1); log["timings"] = tim
    log["gen_tok_s"] = round(tim["predicted_n"] / tim["predicted_ms"] * 1000, 2) if tim["predicted_ms"] else None
    log["prompt_tok_s"] = round(tim["prompt_n"] / tim["prompt_ms"] * 1000, 2) if tim["prompt_ms"] else None
    log["max_ctx_tokens"] = max([((t["usage"] or {}).get("prompt_tokens") or 0) + ((t["usage"] or {}).get("completion_tokens") or 0) for t in log["turns"]] or [0])
    (outdir / "transcript.json").write_text(json.dumps({"messages": msgs, "log": log}, indent=1, default=str))
    return log
