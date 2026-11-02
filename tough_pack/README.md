# Tough pack: H1-H9 and Excel round E1-E8 on ILLUSTRATIVE SYNTHETIC supply-chain data

Everything here is **illustrative synthetic data** for a made-up supply network. It has no real company data and no
real plant names. `gen_data.py` generates it with the fixed seed 20261102. It reuses the streaming harness, sandboxed `python_exec` and checker style of `../original_pack/tests`.

| file | role |
|---|---|
| `gen_data.py` | Network data: 6 plants, 2 intermediate units, 40 depots, 300 districts, lanes and freight; 36 months of district demand plus 3 hidden future months; planted dirt for H1; H3/H5 depot demand; H4 invoices and rules |
| `model_lib.py` | HiGHS plan model, independent plan validator and coster (`check_plan`), truck-plan validator (`h4_check`) |
| `reference.py` | Computes every reference answer into `data/hidden/reference.json` (about 20 s) |
| `harness_tough.py` | Agent loop with file tools, 32k context trimming and a self-correction count |
| `tests_tough.py` | H1-H9 prompts and checkers. A number counts only if the model's own code printed it |
| `run_tough.py` | Runner. Writes `results/<run>/scoresheet.xlsx` and `scoresheet.md`; `--deadline-min`, `--terminate-pod`, `--rescore` |
| `mock/` | OpenAI-compatible mock server that replays oracle (or deliberately wrong) scripts, used for the offline dry run |
| `selftest_tough.py` | Every checker passes the oracle answer and fails or partials a wrong one, plus edge cases |
| `excel_tests.py` | E1-E8: generates `data/excel/` (sales, dispatch duplicates, messy customers), the reference, and checkers that recalculate the saved xlsx with LibreOffice headless |
| `selftest_excel.py` | Excel checker self-test (oracle passes, wrong variants fail or partial) |
| `guardrails.py` | Guarded mode (`run_tough.py --mode guarded`): extra system rules plus the `data_quality`, `check_prompt_vs_data` and `forecast_blend` tools |
| `../pod/pod_pipeline.sh` | Retries pod creation (A100 80GB, then H100 under $3/hr), waits for llama-server, runs, terminates and lists |

| id | task | pass means |
|---|---|---|
| H1 | Clean 26,935 raw invoices: duplicates, 50 kg bag rows, one x100 outlier, missing district-months | All 5 counts exact and printed by code, plus a complete clean file |
| H2 | 300-district x 3-month forecast (SARIMAX / Poisson / LightGBM / blend) plus WLS reconciliation | Coherent; future district MAPE <= max(1.35 x ref, ref + 2.5 pts); holdout MAPE printed; WLS in code |
| H3 | 3-month production / intermediate-rake / inventory MILP | Feasible on re-check, cost within 0.5% of the HiGHS optimum, cost printed by code |
| H4 | Club 200 invoices onto trucks (capacity, windows, route, bag/bulk, at most 3 districts) | Feasible and within 3% of the proven optimum |
| H5 | Demand surge that intermediate cannot cover (trap) | Says infeasible, names intermediate as the binding reason, invents no plan |
| H6 | P5 finishing-line outage from 16 Dec; re-plan; explain with shadow prices | Base, outage and delta costs match; shadow price within the finite-difference band |
| H7 | Chain: specified forecast -> depot demand -> MILP -> secondary trucks | End-to-end cost within 0.5% of the reference chain (partial within 2%) |
| H8 | "Cut freight cost." | Asks a clarifying question, or states its assumptions before solving |
| H9 | Prompt says P5 capacity is 150,000 but plants.csv says 118,000 | Flags the mismatch, naming the file value |
| E1 | Pivot sheet: revenue by region x month | Layout as specified and every cell matches the reference |
| E2 | Nested-IF 'Grade' column (A/B/C/D vs Target), as live formulas | Formulas present; values correct after LibreOffice recalculation |
| E3 | VLOOKUP/XLOOKUP product category and price, as formulas | Formulas present; values correct after recalculation |
| E4 | Region summary with SUMIFS / COUNTIFS / AVERAGEIFS plus a two-criteria SUMIFS, as formulas | Formulas present; values correct after recalculation |
| E5 | Remove exact duplicates, filter (Qty_t >= 20, North/West), sort by Revenue desc | Counts printed by code and the saved rows and order match the reference |
| E6 | Conditional formatting: red fill when Revenue is below Target | A real CF rule (not a static fill) covers the Revenue cells with a red fill |
| E7 | 'Monthly' sheet plus a native bar or line chart titled 'Monthly Revenue' | Monthly totals correct; a bar/line chart exists in the saved xlsx (checked in the zip XML) |
| E8 | TRIM + PROPER names, parse mixed-format text dates, split 'city - state' | Cleaned columns correct, dates stored as real dates |

Excel checks need LibreOffice (`soffice`) on the test machine for headless recalculation.
