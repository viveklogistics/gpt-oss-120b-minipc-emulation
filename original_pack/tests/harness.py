"""Agent loop for llama-server (OpenAI-compatible) with tool calling, timing and a sandboxed python_exec tool.
Plain OpenAI-compatible tool loop (openai client, temperature 0), but streams so the RunPod HTTP
proxy (~100 s idle limit) never times out, and collects llama-server's per-request `timings`."""
import json, os, re, resource, subprocess, sys, time
from pathlib import Path
from openai import OpenAI

PY_LIBS = "numpy, pandas, scipy, statsmodels, scikit-learn, lightgbm, xgboost, highspy, cvxpy, pulp (2.x API), openpyxl"
PYTHON_TIMEOUT_S = int(os.getenv("PY_TIMEOUT_S", "180"))
MAX_TOOL_OUT = 8000

# ------------------------------------------------------------------ python_exec (sandboxed subprocess)
def _limits():
    mem = int(os.getenv("PY_MEM_GB", "6")) * 1024 ** 3
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_CPU, (PYTHON_TIMEOUT_S + 10, PYTHON_TIMEOUT_S + 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 ** 2, 200 * 1024 ** 2))
    os.setsid()

def make_python_exec(workdir: Path):
    counter = {"n": 0}
    def python_exec(code: str):
        counter["n"] += 1
        f = workdir / f"cell_{counter['n']:02d}.py"
        f.write_text(code)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(workdir), "MPLBACKEND": "Agg",
               "OMP_NUM_THREADS": os.getenv("PY_THREADS", "4"), "PYTHONWARNINGS": "ignore", "PYTHONHASHSEED": "0"}
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, f.name], cwd=workdir, env=env, capture_output=True, text=True,
                               timeout=PYTHON_TIMEOUT_S, preexec_fn=_limits)
            out, err, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            out, err, rc = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), \
                           f"TIMEOUT after {PYTHON_TIMEOUT_S}s", -9
        def clip(s, n):
            return s if len(s) <= n else s[: n // 2] + f"\n...[{len(s) - n} chars cut]...\n" + s[-n // 2:]
        return {"exit_code": rc, "stdout": clip(out, 6000), "stderr": clip(err, 2000), "seconds": round(time.time() - t0, 2)}
    return python_exec

PYTHON_TOOL = {"type": "function", "function": {
    "name": "python_exec",
    "description": ("Run a complete Python 3 script in a fresh process (no state is kept between calls, but files written "
                    "in the working directory persist). The working directory contains the task's data files. "
                    f"Available libraries: {PY_LIBS}. Use print() for anything you need to see. "
                    f"Time limit {PYTHON_TIMEOUT_S}s. No internet."),
    "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Full Python script"}},
                   "required": ["code"]}}}

SUBMIT_TOOL = {"type": "function", "function": {
    "name": "submit_answer",
    "description": "Submit the final answer as a JSON object with exactly the keys the task asks for. Call once, at the end.",
    "parameters": {"type": "object", "properties": {"answer": {"type": "object", "description": "Final answer object"}},
                   "required": ["answer"]}}}

# ------------------------------------------------------------------ one streamed chat turn
def chat_turn(client, model, msgs, tools, extra_body, max_tokens):
    t0 = time.time()
    stream = client.chat.completions.create(model=model, messages=msgs, tools=tools, tool_choice="auto",
                                            temperature=float(os.getenv("LLM_TEMPERATURE", "0")), max_tokens=max_tokens,
                                            stream=True, stream_options={"include_usage": True}, extra_body=extra_body)
    content, reasoning, calls, timings, usage, finish = [], [], {}, None, None, None
    for ch in stream:
        ex = ch.model_extra or {}
        if ex.get("timings"): timings = ex["timings"]
        if ch.usage: usage = ch.usage.model_dump()
        if not ch.choices: continue
        c = ch.choices[0]; d = c.delta
        if c.finish_reason: finish = c.finish_reason
        if d.content: content.append(d.content)
        rc = (d.model_extra or {}).get("reasoning_content")
        if rc: reasoning.append(rc)
        for tc in d.tool_calls or []:
            slot = calls.setdefault(tc.index, {"id": None, "name": "", "args": ""})
            if tc.id: slot["id"] = tc.id
            if tc.function and tc.function.name: slot["name"] += tc.function.name
            if tc.function and tc.function.arguments: slot["args"] += tc.function.arguments
    return {"content": "".join(content), "reasoning": "".join(reasoning),
            "tool_calls": [calls[k] for k in sorted(calls)], "timings": timings, "usage": usage,
            "finish_reason": finish, "wall_s": time.time() - t0}

def _parse_json_answer(text):
    """Fallback when the model answers in text instead of calling submit_answer."""
    for m in reversed(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S)):
        try: return json.loads(m)
        except Exception: pass
    m = re.search(r"(\{.*\})", text or "", re.S)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    return None

# ------------------------------------------------------------------ the agent loop
def run_agent(system, user, tools, funcs, outdir: Path, base_url, model="local", max_steps=25,
              wall_limit_s=1200, max_tokens=8192, reasoning_effort=None):
    client = OpenAI(base_url=base_url, api_key=os.getenv("LLM_API_KEY", "none"), timeout=900, max_retries=1)
    extra = {}
    if reasoning_effort:  # gpt-oss chat template knob; other templates ignore it
        extra["chat_template_kwargs"] = {"reasoning_effort": reasoning_effort}
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    log = {"tool_calls": [], "turns": [], "answer": None, "answer_via": None, "final_text": "", "stop": None}
    tim = {"prompt_n": 0, "prompt_ms": 0.0, "predicted_n": 0, "predicted_ms": 0.0}
    t_start = time.time()
    for step in range(max_steps):
        if time.time() - t_start > wall_limit_s:
            log["stop"] = f"wall limit {wall_limit_s}s"; break
        try:
            r = chat_turn(client, model, msgs, tools, extra, max_tokens)
        except Exception as e:
            log["stop"] = f"server error: {type(e).__name__}: {e}"[:500]; break
        if r["timings"]:
            for k in tim: tim[k] += float(r["timings"].get(k, 0) or 0)
        log["turns"].append({k: r[k] for k in ("content", "reasoning", "tool_calls", "timings", "usage", "finish_reason", "wall_s")})
        am = {"role": "assistant", "content": r["content"] or ""}
        if r["reasoning"]: am["reasoning_content"] = r["reasoning"]
        if r["tool_calls"]:
            am["tool_calls"] = [{"id": c["id"] or f"call_{step}_{i}", "type": "function",
                                 "function": {"name": c["name"], "arguments": c["args"] or "{}"}}
                                for i, c in enumerate(r["tool_calls"])]
        msgs.append(am)
        if not r["tool_calls"]:
            log["final_text"] = r["content"]
            if log["answer"] is None:
                a = _parse_json_answer(r["content"])
                if a is not None: log["answer"], log["answer_via"] = a, "json_in_text"
            log["stop"] = "final_answer" if r["finish_reason"] != "length" else "max_tokens"
            break
        done = False
        for c in am["tool_calls"]:
            name, raw = c["function"]["name"], c["function"]["arguments"]
            rec = {"step": step, "tool": name, "args": raw[:4000], "valid_json": True, "error": None}
            try:
                args = json.loads(raw or "{}")
            except Exception as e:
                args, rec["valid_json"] = None, False
                out = {"error": f"arguments were not valid JSON: {e}"}
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
                else:
                    out = {"error": f"unknown tool {name}"}
            if isinstance(out, dict) and (out.get("error") or out.get("exit_code") not in (None, 0)):
                rec["error"] = str(out.get("error") or out.get("stderr", ""))[-300:]
            res = json.dumps(out, default=str)
            rec["result"] = res[:MAX_TOOL_OUT]
            log["tool_calls"].append(rec)
            print(f"   [{step}] {name} -> {res[:160]}", file=sys.stderr, flush=True)
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": res[:MAX_TOOL_OUT]})
        if done:
            log["final_text"] = r["content"]; log["stop"] = "submitted"; break
    else:
        log["stop"] = f"max_steps {max_steps}"
    log["wall_s"] = round(time.time() - t_start, 1)
    log["timings"] = tim
    log["gen_tok_s"] = round(tim["predicted_n"] / tim["predicted_ms"] * 1000, 2) if tim["predicted_ms"] else None
    log["prompt_tok_s"] = round(tim["prompt_n"] / tim["prompt_ms"] * 1000, 2) if tim["prompt_ms"] else None
    (outdir / "transcript.json").write_text(json.dumps({"messages": msgs, "log": log}, indent=1, default=str))
    return log
