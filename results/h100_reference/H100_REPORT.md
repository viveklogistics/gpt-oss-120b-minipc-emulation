# Can gpt-oss-120b on llama.cpp do agentic ML / OR / Excel work? A cloud-GPU test report

*Run date: 2 November 2026 (times in IST, UTC+5:30). All task data is **illustrative synthetic data** (a made-up product
supply chain). It contains no real company data. Updated the same day with a **guarded rerun** of the tough pack and the
Excel round (section 4.6).*

## 1. Purpose

We wanted to know whether **gpt-oss-120b, served locally by llama.cpp**, can do real multi-step analytics work by itself.
That means calling tools, writing and running Python, checking its own results, and finishing. The work tested covers
forecasting, mixed-integer planning, truck loading, what-if analysis and everyday Excel.

The answer decides whether a **128 GB unified-memory mini PC** is worth buying to run this model offline.
We ran the model on a rented NVIDIA GPU first, so we could judge **capability** before spending on hardware.
Speed on the mini PC is only **estimated** here; it was not measured.

## 2. Setup

| item | value |
|---|---|
| Model | gpt-oss-120b, MXFP4 GGUF (`ggml-org/gpt-oss-120b-GGUF`, `gpt-oss-120b-MXFP4.gguf`, about 63 GB) |
| Server | llama.cpp `llama-server` build **b12024-ddf48f85c**, prebuilt CUDA 12.8 binaries. Flags: `--jinja -c 32768 -ngl 99 -np 1` (guarded rerun: `-c 131072`) |
| Context | Baseline: 32,768 tokens; the tough-pack harness trims old tool outputs once the context passes 20,000 tokens. Guarded rerun: 131,072 tokens, trimming only above 118,880 tokens (no test came near it) |
| Reasoning | `reasoning_effort` = **medium**, temperature 0 |
| Hardware | RunPod **NVIDIA H100 NVL** (Community Cloud, $2.59/hr). An A100 80GB was tried first but none was available |
| Client | OpenAI Python client in streaming mode, run from a separate machine through the RunPod HTTP proxy |
| Tools given to the model | `python_exec` (sandboxed; numpy, pandas, scipy, statsmodels, scikit-learn, lightgbm, xgboost, highspy, cvxpy, pulp, openpyxl), file read/list, `submit_answer` |

## 3. Test design and scoring

Three packs were run:

* **Original pack (T1-T5):** 5 shorter tests.
  * T1 was a geo-lookup tool-calling task on public map data about a real site. It is **not** part of the public kit.
  * T2-T5 used synthetic data.
* **Tough pack (H1-H9):** a synthetic supply network with 6 plants, 2 intermediate units, 40 depots, 300 districts and
  36 months of history. It has planted data problems, a trap and a chained task.
* **Excel round (E1-E8):** small synthetic sales and dispatch workbooks. The results are checked by **opening the saved
  `.xlsx`** and recalculating it in LibreOffice headless. The checks confirm that formulas are present and that values
  are correct after recalculation, and that conditional-formatting rules and chart objects exist.

Scoring rules:

* Every checker compares the model's **saved files and answers** with a hidden reference that the model never sees.
  Plans are re-checked for feasibility, and costs are recomputed independently.
* **A number counts only if the model's own code printed it.** A correct number that appears only in prose is a fail.
* Verdicts are `pass`, `partial` or `fail`, each with a written reason.
  * Tough pack limits: up to 40 steps per test, 8,192 max tokens per turn, and a wall-clock limit per test (for example 540 s for H4).
* All checkers were validated **offline before** the GPU run. A mock server replayed oracle solutions, which all had to
  pass, and deliberately wrong solutions, which all had to fail or get partial, through the real harness.

## 4. Results

### 4.1 Original pack: 5 / 5 pass (run at 13:37 IST, 3.5 min wall)

| test | task | verdict | tool calls | tool errors | gen tok/s | prompt tok/s |
|---|---|---|---|---|---|---|
| T1 | Tool-calling geo lookup on public map data (not in public kit) | pass | 13 | 0 | 176.0 | 1786.83 |
| T2 | SARIMAX + Poisson GLM blend, 12-month backtest | pass. All three MAPEs within 0.0 pp of the reference (blend 2.1664 %) | 3 | 2 | 178.48 | 2267.99 |
| T3 | Club 12 invoices onto trucks (MILP) | pass. Feasible; cost Rs 118,500 = proven optimum, 6 trucks | 8 | 2 | 176.62 | 2009.67 |
| T4 | KKT conditions of a 3-variable QP | pass. x, λ, μ, objective −16.5, active sets all correct | 9 | 0 | 177.57 | 1719.64 |
| T5 | 4×6 transport LP, duals, what-if | pass. Cost Rs 110,230,000; 6/6 + 4/4 duals; what-if Rs 109,730,000 | 9 | 1 | 176.73 | 2130.32 |

### 4.2 Tough pack H1-H9: 2 pass / 3 partial / 4 fail

| test | task | verdict | reason (from the checker) | tool calls | tool errors | self-corr. | wall s | gen tok/s |
|---|---|---|---|---|---|---|---|---|
| H1 | Clean 26,935 raw invoices | **fail** | Duplicates (37) and bag rows (58) right. Outliers: it removed 221 rows with a 3-sigma rule, but only 1 row was planted. Missing district-months: it reported 198, the true count is 23. Clean total therefore wrong | 11 | 0 | 0 | 54.3 | 177.69 |
| H2 | 300-district × 3-month forecast + WLS reconciliation | **partial** | Coherent, and WLS (MinT-diagonal) code present. Future district MAPE 13.751 % vs pass band ≤ 10.067 % (reference 7.457 %). Holdout MAPE not reported (it ended in prose with no JSON) | 5 | 0 | 0 | 32.1 | 177.55 |
| H3 | 3-month production / intermediate-rake / inventory MILP | **pass** | Feasible on re-check; gap to the HiGHS optimum 0.0 %; cost printed by code | 22 | 1 | 1 | 63.2 | 151.36 |
| H4 | Club 200 invoices onto trucks (windows, routes, ≤ 3 districts) | **partial** | Saved plan feasible, 85 trucks, cost Rs 1,408,200 vs optimum Rs 1,397,400 (gap 0.773 %). It hit the 540 s wall limit before submitting a cost. 16 self-corrections | 37 | 18 | 16 | 568.2 | 164.17 |
| H5 | Trap: demand surge intermediate cannot cover | **pass** | Said infeasible, named intermediate as the binding limit, did not invent a plan | 15 | 2 | 2 | 38.5 | 175.86 |
| H6 | Finishing-line outage from 16 Dec: re-plan + shadow prices | **partial** | Base, outage and delta costs all correct; shadow price value correct. Its code printed −71.776, but it reported +71.776 (a sign convention it explained), so the strict "printed by code" rule failed that one number | 16 | 3 | 3 | 84.7 | 174.41 |
| H7 | Chain: forecast → plan → secondary trucks, end-to-end cost | **fail** | No answer. After 32 tool calls the context reached 32,768 tokens (39 trims). The model then emitted a malformed tool-call JSON (unterminated string), which llama-server rejected with HTTP 500 | 32 | 10 | 6 | 305.0 | 170.79 |
| H8 | Vague ask: "Cut freight cost." | **fail** | Asked no clarifying question and stated no assumptions. It solved straight away and answered "5 % cut, Rs 91,262,271 savings" | 15 | 4 | 4 | 38.0 | 175.50 |
| H9 | Prompt says P5 capacity 150,000 t; file says 118,000 t | **fail** | Silently used the file value (cost matches the file-based reference), but never flagged the contradiction | 14 | 1 | 1 | 38.7 | 176.13 |

### 4.3 Excel round E1-E8: 6 pass / 1 partial / 1 fail

| test | task | verdict | reason (from the checker) | tool calls | wall s | gen tok/s |
|---|---|---|---|---|---|---|
| E1 | Pivot sheet, region × month revenue | **pass** | 30/30 cells correct, regions sorted | 4 | 6.0 | 180.52 |
| E2 | Nested-IF grade column as formulas | **pass** | 150/150 formula rows; values correct after recalculation | 2 | 7.2 | 181.52 |
| E3 | VLOOKUP/XLOOKUP from a second sheet | **pass** | VLOOKUP formulas for Category and Price: 150/150 each, correct after recalculation | 6 | 12.3 | 177.98 |
| E4 | SUMIFS / COUNTIFS / AVERAGEIFS summary (original wording) | **fail** | Formulas were well formed, and the two-criteria SUMIFS was correct. But it read "one row per region A-Z" as literal regions named A, B, C … instead of the real regions sorted A-Z, so 0/15 cells matched. The prompt wording was ambiguous, but the data shows the real region names | 5 | 9.5 | 178.56 |
| E5 | Remove duplicates, filter, sort | **pass** | 47/47 rows in the exact order; counts 157 / 7 / 47 printed by code | 4 | 5.6 | 180.05 |
| E6 | Conditional formatting: red below target | **pass** | Expression rule `H2<I2` on H2:H151 with Excel's preset light-red fill (FFC7CE) | 7 | 9.3 | 179.02 |
| E7 | Bar/line chart | **pass** | Native bar chart titled "Monthly Revenue" plots the Total_Revenue range; monthly values correct | 5 | 8.4 | 179.14 |
| E8 | TRIM, PROPER, dates, split column | **partial** | Names, cities and states 40/40, all dates stored as real dates, but 6 of 40 day-first dates were parsed month-first (34/40 correct) | 5 | 8.8 | 177.93 |

**Checker corrections made after the run (disclosed).** Two checker bugs were found while reading the results. Both were fixed,
re-validated with the offline self-tests, and the saved transcripts were rescored with no new model calls:

* E5 was first scored **partial**. The checker did not unwrap an answer given as `{"answer": {...}}`. All three counts were
  correct and printed by code.
* E6 was first scored **partial**. The red-fill test rejected Excel's standard "light red" preset (`FFC7CE`, stored with alpha `00`).

Without these two fixes, the Excel round would read 4 pass / 3 partial / 1 fail. No other verdict changed.

### 4.4 Totals and speed (tough + Excel, 17 tests)

| metric | H1-H9 | E1-E8 | all 17 |
|---|---|---|---|
| verdicts | 2 pass / 3 partial / 4 fail | 6 pass / 1 partial / 1 fail | 8 pass / 4 partial / 5 fail |
| tool calls | 167 | 38 | 205 |
| tool errors | 39 | 1 | 40 |
| self-corrections (a failed Python call later followed by a successful one) | 33 | 1 | 34 |
| model wall time | 1,222.7 s | 67.1 s | 1,289.8 s (≈ 21.5 min) |
| generation tok/s (median, range) | 175.5 (151.36-177.69) | 179.08 (177.93-181.52) | 177.69 (151.36-181.52) |
| prompt tok/s (median) | 2,239.25 | 2,368.94 | 2,333.46 |

**Mini-PC speed (ESTIMATE, not measured).** We scaled the measured H100 NVL generation speed by the memory-bandwidth ratio:
about 3.9 TB/s against about 256 GB/s, a factor of 15.2. That gives about **11.5-11.8 tok/s** generation on a
128 GB unified-memory mini PC with 256 GB/s bandwidth. Treat this as a rough upper-bound guide: prompt processing on such a
machine will be far slower than the 2,000+ tok/s seen here, and multi-step agent runs re-read long contexts. Measure on the real device before deciding.

### 4.5 Cost and pod time

| pod | use | created | terminated | minutes | cost at $2.59/hr |
|---|---|---|---|---|---|
| tough pod 1 (H100 NVL) | H1-H3, then a stalled H4 | 14:36:40 | 14:54:13 | ≈ 17.6 | ≈ $0.76 |
| tough pod 2 (H100 NVL) | H4-H9 and E1-E8 | 14:54:53 | 15:16 | ≈ 21-22 | ≈ $0.91-0.95 |
| **total, tough + Excel** | | | | **≈ 39 min** | **≈ $1.67-1.71** (budget $3) |

Pod 1 was cut short twice:

1. **H4 stalled.** The first H4 attempt hung on a streaming request where the server was idle but the client kept waiting.
   The client timeout was lowered from 900 s to 240 s, and that attempt was discarded with no score.
2. **The pod was terminated by mistake.** The script that resumed the run had a bug and terminated pod 1. A second pod
   of the same GPU type, with the same build and settings, re-ran H4-H9 and the Excel round.

Every pod was terminated, and RunPod's pod list was confirmed empty afterwards. The original 5-test pack ran earlier
the same day on another H100 NVL pod for about 7 minutes (13:30-13:37); its hourly price is not in our logs.

### 4.6 Guarded rerun (15:46-16:10 IST): same model, same tests, extra rules and tools

**Why.** The baseline failures were mostly about judgement (H1 outliers, H8 vague ask, H9 prompt-vs-file conflict),
forecast accuracy (H2) and context (H7). The guarded mode tests whether a thin layer of rules and helper tools fixes
those, without changing the model, the data, the checkers or the seed (20261102).

**What guarded mode adds** (`tough_pack/guardrails.py`, `run_tough.py --mode guarded`):

1. **Context 131,072** (`llama-server -c 131072`; it fitted on the H100 NVL, so the 65,536 fallback was not needed).
2. **`data_quality` tool**, required first by the system prompt. It only *flags* exact duplicates, repeated ids, nulls,
   unit-suspect rows, outlier candidates (extreme ratio to the group median, robust z, 3-sigma count) and missing
   group-months. It changes nothing. The rules allow dropping an outlier only with a specific justification, never on 3-sigma alone.
3. **`check_prompt_vs_data` tool**: it compares numbers stated in the prompt with the data files and reports mismatches.
   The rules require telling the user about any mismatch (both values, the file, and which value was used).
4. **Vague-goal rule**: for a vague goal, ask a clarifying question and stop, or list assumptions before any solver.
5. **`forecast_blend` tool**: per series 50/50 SARIMAX(1,1,1)(0,1,1,12) + Poisson GLM, WLS (MinT-diagonal)
   reconciliation district → plant → total, returning the holdout MAPE.
6. Numbers must come from tool output (as before).

**Changes to the tests themselves (disclosed).**

* **E4 prompt fixed in both modes.** "one row per region A-Z" now reads "one row for each distinct region name that appears in
  the Sales sheet's Region column, sorted alphabetically (A to Z)". The meaning is unchanged, so the original baseline E4 is
  **not rescored** (it stays fail). A separate baseline-mode run of E4 with the fixed prompt **passed** (15/15 formula cells
  and values, 16:10 IST).
* **E8 now uses fictional town and province names** instead of real Indian cities. The messiness pattern and the random
  draws are the same. Baseline E8 ran on the old file and keeps its verdict.
* The "printed by code" rule also accepts numbers printed by the three guard tools, and H2's WLS check accepts a successful
  `forecast_blend` call. We rescored a copy of the baseline transcripts with the new checkers: no H verdict or detail changed.
* All guard tools and the guarded mock path were validated offline first: the mock oracle passed 17/17 in guarded mode,
  deliberately wrong solutions all failed or got partial, and `check_prompt_vs_data` flagged only the planted H9 conflict
  across all 17 tests (no false positives).

**Results: 10 pass / 4 partial / 3 fail (baseline 8 / 4 / 5).**

| test | baseline | guarded | tool calls (base → guarded) | of which guard tools | tool errors (base → guarded) | self-corr. (base → guarded) | gen tok/s (base → guarded) |
|---|---|---|---|---|---|---|---|
| H1 | fail | **partial** | 11 → 11 | 1 | 0 → 0 | 0 → 0 | 177.69 → 120.27 |
| H2 | partial | **pass** | 5 → 13 | 3 | 0 → 0 | 0 → 0 | 177.55 → 175.79 |
| H3 | pass | pass | 22 → 29 | 5 | 1 → 1 | 1 → 1 | 151.36 → 170.58 |
| H4 | partial | partial | 37 → 15 | 1 | 18 → 4 | 16 → 4 | 164.17 → 174.70 |
| H5 | pass | **fail** | 15 → 26 | 4 | 2 → 12 | 2 → 0 | 175.86 → 169.26 |
| H6 | partial | partial | 16 → 19 | 0 | 3 → 4 | 3 → 4 | 174.41 → 172.56 |
| H7 | fail | fail | 32 → 25 | 2 | 10 → 7 | 6 → 7 | 170.79 → 174.06 |
| H8 | fail | **pass** | 15 → 0 | 0 | 4 → 0 | 4 → 0 | 175.50 → 180.46 |
| H9 | fail | **pass** | 14 → 14 | 3 | 1 → 0 | 1 → 0 | 176.13 → 173.41 |
| E1 | pass | pass | 4 → 7 | 2 | 0 → 0 | 0 → 0 | 180.52 → 178.09 |
| E2 | pass | pass | 2 → 5 | 1 | 0 → 0 | 0 → 0 | 181.52 → 176.99 |
| E3 | pass | **fail** | 6 → 3 | 0 | 0 → 0 | 0 → 0 | 177.98 → 178.24 |
| E4 | fail (old wording) | pass (fixed wording) | 5 → 6 | 0 | 0 → 0 | 0 → 0 | 178.56 → 175.90 |
| E5 | pass | pass | 4 → 3 | 0 | 0 → 0 | 0 → 0 | 180.05 → 179.07 |
| E6 | pass | pass | 7 → 5 | 0 | 1 → 0 | 1 → 0 | 179.02 → 176.72 |
| E7 | pass | pass | 5 → 6 | 0 | 0 → 0 | 0 → 0 | 179.14 → 176.29 |
| E8 | partial | partial | 5 → 6 | 0 | 0 → 0 | 0 → 0 | 177.93 → 177.45 |

| metric | baseline | guarded |
|---|---|---|
| H1-H9 verdicts | 2 pass / 3 partial / 4 fail | 4 pass / 3 partial / 2 fail |
| E1-E8 verdicts | 6 pass / 1 partial / 1 fail | 6 pass / 1 partial / 1 fail |
| all 17 | 8 / 4 / 5 | **10 / 4 / 3** |
| tool calls (H / E) | 167 / 38 | 152 / 41 (22 of them guard-tool calls) |
| tool errors (H / E) | 39 / 1 | 28 / 0 |
| self-corrections (H / E) | 33 / 1 | 16 / 0 |
| model wall time | 1,289.8 s | 1,413.3 s |
| generation tok/s, median (range) | 177.69 (151.36-181.52) | 175.90 (120.27-180.46) |
| prompt tok/s, median | 2,333.46 | 2,233.27 |

**What changed, test by test (from the transcripts and checker details).**

* **H8 fixed by the rule.** The model asked five clarifying questions (scope, target, constraints, horizon, data) and
  made no tool calls.
* **H9 fixed by the tool.** `check_prompt_vs_data` reported P5_Plover 150,000 t (prompt) against 118,000 t (`plants.csv`).
  The answer stated the mismatch, said it used the file value, and its cost matched the file-based reference.
* **H2 fixed by the tool, not by better modelling.** The model called `forecast_blend` and submitted its output: future
  district MAPE 7.585 % (pass band ≤ 10.067 %, reference 7.457 %), holdout MAPE 9.272 % reported (reference 8.997 %).
* **H1 improved from fail to partial.** Duplicates (37), bag rows (58), missing district-months (23) and the clean total
  were right. It still removed 8 "outliers" instead of the 1 planted row. **This came partly from our tool:**
  `data_quality` lists rows at ≥ 10× *or* ≤ 0.05× the district median as "extreme". That caught the planted 83× row and
  7 genuinely small orders. The model dropped all 8, citing that band as its justification. A tighter flag is an
  obvious fix for a future run. We did not change it after seeing the result.
* **H5 regressed from pass to fail.** The model could not build the MILP. 6 of its 11 failed Python calls contained
  leaked chat-format tokens (`<|end|><|start|>assistant<|channel|>…`) inside the code string, and others had indentation
  errors. It gave up with "status: failed" and never reached the infeasibility finding. It still named intermediate but did not
  say "infeasible". This looks like a generation/format failure, not something the guard tools caused, but it happened in
  guarded mode, so it counts.
* **E3 regressed from pass to fail.** It wrote `=XLOOKUP(...)` through openpyxl without the `_xlfn.` prefix that the
  xlsx format needs for newer functions, so every lookup showed `#NAME?` after recalculation (0/150). As an offline check
  only, adding the prefix to a copy made all 150 rows correct. The verdict stays fail. In the baseline it used VLOOKUP and passed.
* **H7 still fails, now for a different reason.** With 131k context it never came close to the limit (peak 13,975
  tokens). The run ended when a streaming request went silent for 240 s (client timeout) after 25 tool calls, before any
  stage of the chain had been answered.
* **H4 used fewer calls** (15 against 37) and far fewer errors (4 against 18). Its plan was feasible with 85 trucks but
  1.288 % above optimum, and the run ended on a llama-server parse error ("output does not match the expected
  peg-native format") before it submitted a cost. E6 ended on the same server error but had already saved a correct file.
* **E8** parsed only 13 of 40 mixed-format dates correctly (baseline 34/40).
* **H6** unchanged: all four values correct, but the shadow price was again re-typed as a positive number rather than printed by code.

**Did the model follow the rules?** Only partly. `data_quality` was called in 9 of the 17 tests (not in H6 or E3-E8;
in H8 asking first was the right move). `check_prompt_vs_data` was called in 4 tests (H2, H7, H9, E1), which included
the one test where it mattered. It usually came after `list_files` and a few `read_file` calls, not literally first.
`forecast_blend` was used in H2, which was the one test where it fitted.

**Bottom line.** Rules and tools fixed the judgement failures they target (H8, H9) and the forecast-accuracy gap (H2),
and cut H4 errors. They did not fix long chains (H7). Two new failures (H5, E3) came from code-generation and format
problems. With one run per test, a single test flipping either way is within run-to-run variation. Treat the net
+2 passes as indicative, not proven.

**Pod and cost.** One H100 NVL (Community Cloud, $2.59/hr), created 15:44:26 IST and terminated 16:10 IST,
after both the guarded run and the fixed-prompt E4 run had finished. RunPod's pod list was confirmed empty afterwards.
Pod time ≈ 26.1 min, so **≈ $1.13**. The local watchdog and the in-pod auto-stop were set to 1.1 h as a cap.

## 5. Strengths

* **Solid tool calling and Python use.** Across 205 tool calls in the H and E packs there was 1 malformed tool call, and
  it came only when the context was completely full. It recovers from its own errors (34 self-corrections).
* **Optimisation is strong when the problem is well posed.** It hit the exact optimum on the 3-month MILP (H3) and on
  the T3/T5 problems. Its 200-invoice truck plan was feasible and within 0.8 % of optimal (H4). It got the outage what-if
  deltas and shadow price right (H6).
* **It recognised the infeasibility trap (H5).** It reported that the demand surge could not be met, blamed intermediate,
  and did not make up a plan (baseline run; in the guarded rerun H5 failed on broken code generation, see 4.6).
* **Excel is good.** It writes real formulas (nested IF, VLOOKUP, SUMIFS), conditional-formatting rules and native
  charts that survive recalculation. Each Excel task took under 15 s.
* **Fast on an H100.** About 175-180 tok/s generation and 2,000+ tok/s prompt processing.

## 6. Weaknesses

* **It does not question the task.** It asked no clarifying question on a vague request (H8). It never flagged that the
  prompt contradicted the data file (H9), even though it silently used the file value. It made a literal misreading
  in E4 rather than checking the data.
* **Data-cleaning judgement.** It used a blanket 3-sigma rule instead of finding the one planted ×100 error, and it
  miscounted missing months (H1). It parsed some day-first dates as month-first (E8).
* **Long chains run out of context.** With a 32k context, the chained task (H7) filled the window and ended with a
  malformed tool call and no answer. The 200-invoice MILP (H4) used its full wall-time budget.
* **Reporting discipline.** It sometimes ended in prose with no structured answer (H2), or re-typed numbers by hand
  with a flipped sign (H6). Under strict "printed by code" scoring, both cost points.
* **Forecast accuracy was mediocre.** Its future district MAPE was 13.75 % against a reference of 7.46 % (H2).

## 7. Limitations

* There was **one run per test** at temperature 0. With no repeats, small differences are not statistically meaningful.
* The run used medium reasoning effort and a 32k context only. A larger context or high effort might help H7 and H4,
  but was not tested.
* The tests ran on an H100, **not on the target mini PC**. Mini-PC speed is an estimate from the bandwidth ratio.
* H1-H3 ran on pod 1 and H4-H9 plus the Excel round on pod 2. Both used the same GPU type, build, quant and settings.
* The prompts were written by us. E4's original "A-Z" wording was ambiguous; it was fixed for the guarded rerun (4.6). The task data is synthetic and simpler than real
  company data.
* The guarded rerun used a different context size (131k against 32k) as well as the new rules and tools, so the
  comparison does not isolate the effect of each change.
* Two Excel checker bugs were fixed after the run and are disclosed in 4.3. The verdicts follow strict rules that
  some readers may find harsh (H6).

## 8. How to reproduce

The public kit (`gptoss120b_agentic_test_kit.zip`) contains the data generators, tests, checkers, runners, a mock server and the RunPod scripts.

```bash
pip install -r requirements.txt          # plus LibreOffice for the Excel checks
cd original_pack && python tests/gen_data.py && python tests/reference.py && python tests/selftest_checkers.py && cd ..
cd tough_pack && python gen_data.py && python reference.py && python selftest_excel.py && cd ..
# point at any OpenAI-compatible llama-server (llama-server --jinja -c 32768 -ngl 99 -m gpt-oss-120b-MXFP4.gguf)
python original_pack/run_all.py --base-url http://HOST:8000/v1
python tough_pack/run_tough.py  --base-url http://HOST:8000/v1
# or on RunPod (needs RUNPOD_API_KEY in the environment; always check `python pod/runpod_ctl.py list` afterwards)
HOURS=0.8 BUDGET=3 bash pod/pod_pipeline.sh
# guarded mode (rules + data_quality / check_prompt_vs_data / forecast_blend tools), 131k context
MODE=guarded CTX=131072 HOURS=1.1 OUT=tough_pack/results/guarded bash pod/pod_pipeline.sh
python tough_pack/run_tough.py --rescore tough_pack/results/guarded --mode guarded   # rescoring a guarded run needs --mode guarded
```

The data seeds are fixed. Regenerating the data reproduces the same references; we checked this, and only the timing
field differs. Model outputs will vary with the llama.cpp build, quant and sampling settings.
