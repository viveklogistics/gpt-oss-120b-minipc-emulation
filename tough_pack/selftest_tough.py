"""Checker self-test: re-score the mock dry runs (oracle answers must all pass, wrong answers must not pass) and
probe edge cases of the text-based checkers (H5, H8, H9) with hand-built logs."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from tests_tough import TESTS
ok = True
def expect(name, got, allowed):
    global ok
    good = got in allowed; ok &= good; print(f"{'OK ' if good else 'BAD'} {name}: {got} (expected {'/'.join(allowed)})")
for run, allowed in (("dryrun_mock_correct", ("pass",)), ("dryrun_mock_wrong", ("partial", "fail"))):
    if not (HERE / "results" / run).exists(): print(f"skip {run}: run the mock dry run first (see README)"); continue
    for wd in sorted((HERE / "results" / run).iterdir()):
        if wd.name.startswith("E"): continue   # the mock replays H oracles only; Excel checkers: selftest_excel.py
        if (wd / "transcript.json").exists():
            log = json.loads((wd / "transcript.json").read_text())["log"]
            expect(f"{run}/{wd.name}", TESTS[wd.name]["check"](log, wd)[0], allowed)
def L(final="", answer=None, turns=(), calls=(), stop="submitted"):
    return {"final_text": final, "answer": answer, "turns": [{"content": c} for c in turns], "tool_calls": list(calls), "stop": stop}
py = lambda code, out: {"tool": "python_exec", "args": json.dumps({"code": code}), "result": json.dumps({"stdout": out}), "error": None, "valid_json": True, "step": 0}
expect("H8 asks a question only", TESTS["H8"]["check"](L("Which freight do you mean, primary or secondary? And what is the horizon?", stop="final_answer"), None)[0], ("pass",))
expect("H8 solves silently", TESTS["H8"]["check"](L("Done.", {"total": 1}, ["", ""], [py("import highspy; h.run()", "1")]), None)[0], ("fail",))
expect("H5 infeasible, no reason", TESTS["H5"]["check"](L("", {"status": "infeasible", "explanation": "the model has no solution"}, [], [py("x", "Infeasible")]), None)[0], ("partial",))
expect("H5 invents a plan", TESTS["H5"]["check"](L("", {"status": "Optimal", "total_cost_rs": 5e9, "explanation": "ok"}, [], [py("x", "5000000000")]), None)[0], ("fail",))
expect("H9 trusts prompt", TESTS["H9"]["check"](L("Solved with P5 at 150,000.", {"total_cost_rs": 4721914820, "notes": "used 150000"}, [], [py("x", "4721914820")]), None)[0], ("fail",))
print("ALL CHECKER SELF-TESTS OK" if ok else "SOME SELF-TESTS FAILED"); sys.exit(0 if ok else 1)
