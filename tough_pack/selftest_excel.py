"""Every E checker must pass the oracle workbook and fail or partial a deliberately wrong one."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent / "mock"))
from excel_tests import E_TESTS
from excel_oracle import solve
bad = 0
for tid, T in E_TESTS.items():
    for wrong in (False, True):
        wd = Path(tempfile.mkdtemp()); T["setup"](wd); res = solve(tid, wd, wrong) or {}
        log = {"answer": {"file": f"{tid.lower()}.xlsx", **res},
               "tool_calls": [{"tool": "python_exec", "error": False, "result": json.dumps({"stdout": json.dumps(res)})}]}
        v, det = T["check"](log, wd); exp_ok = (v == "pass") if not wrong else (v != "pass")
        bad += not exp_ok
        print(f"{tid} {'WRONG ' if wrong else 'oracle'} -> {v:8s} {'OK' if exp_ok else 'MISMATCH'}  {json.dumps(det, default=str)[:230]}")
print("ALL EXCEL CHECKER SELF-TESTS OK" if not bad else f"{bad} MISMATCHES")
