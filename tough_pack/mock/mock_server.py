"""OpenAI-compatible streaming mock of llama-server for the dry run. It replays the oracle scripts as python_exec calls,
then submits the ANSWER_JSON printed by the last cell, then gives a short final message. MOCK_WRONG=1 replays the
wrong variants. It also emits llama.cpp-style 'timings' so the tok/s plumbing is exercised."""
import json, os, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import oracle
from tests_tough import TESTS
WRONG = os.getenv("MOCK_WRONG") == "1"

DQ_FILE = {"H1": "h1_invoices_raw.csv", "H2": "demand_clean.csv", "H3": "h3_depot_demand.csv", "H4": "h4_invoices.csv",
           "H5": "h5_depot_demand.csv", "H7": "demand_clean.csv", "E5": "sales_dups.xlsx", "E8": "customers.xlsx"}

def turns_for(test, guarded=False):
    turns, pending = [], None
    if guarded:   # guarded mode: exercise the guard tools first, as the guarded system prompt requires
        turns.append({"content": "Checking the prompt against the data first.", "call": ("check_prompt_vs_data", {})})
        f = DQ_FILE.get(test, "sales.xlsx" if test.startswith("E") else "h3_depot_demand.csv")
        turns.append({"content": "", "call": ("data_quality", {"path": f})})
        if test == "H2":
            turns.append({"content": "", "call": ("forecast_blend", {"demand_path": "demand_clean.csv", "hierarchy_path": "districts.csv",
                                                                       "calendar_path": "calendar.csv", "out_path": "forecast_blend_check.csv"})})
    for kind, val in oracle.script(test, WRONG):
        if kind == "say": pending = val
        else: turns.append({"content": pending or "", "call": ("python_exec", {"code": val})}); pending = None
    turns.append({"content": "", "call": "SUBMIT"})
    turns.append({"content": "Done - submitted.", "call": None})
    return turns

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b'{"data":[{"id":"mock"}],"status":"ok"}')
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = req["messages"]; user = next(m["content"] for m in msgs if m["role"] == "user")
        test = next(k for k, v in TESTS.items() if v["user"] == user)
        n = sum(1 for m in msgs if m["role"] == "assistant"); guarded = any(t["function"]["name"] == "data_quality" for t in req.get("tools") or [])
        turns = turns_for(test, guarded); t = turns[min(n, len(turns) - 1)]
        call = t["call"]
        if call == "SUBMIT":
            last = [m for m in msgs if m["role"] == "tool"][-1]["content"]
            stdout = json.loads(last).get("stdout", "")
            mm = re.search(r"ANSWER_JSON: (\{.*\})", stdout)
            call = ("submit_answer", {"answer": json.loads(mm.group(1)) if mm else {"error": "no answer"}})
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        def send(obj): self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode()); self.wfile.flush()
        base = {"id": "m", "object": "chat.completion.chunk", "created": int(time.time()), "model": "mock"}
        if t["content"]: send({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": t["content"]}, "finish_reason": None}]})
        if call:
            send({**base, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": f"c{n}", "type": "function",
                  "function": {"name": call[0], "arguments": json.dumps(call[1])}}]}, "finish_reason": None}]})
        send({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if call else "stop"}]})
        send({**base, "choices": [], "usage": {"prompt_tokens": 1000 + 300 * n, "completion_tokens": 200, "total_tokens": 1200 + 300 * n},
              "timings": {"prompt_n": 1000, "prompt_ms": 500.0, "predicted_n": 200, "predicted_ms": 1000.0}})
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
