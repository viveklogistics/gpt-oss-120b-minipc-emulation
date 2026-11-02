# Tough pack scoresheet: gpt-oss-120b MXFP4, llama.cpp b12024, H100 NVL (RunPod COMMUNITY); H1-H3 on pod 1, H4-H9 and E1-E8 on pod 2

- **label**: gpt-oss-120b MXFP4, llama.cpp b12024, H100 NVL (RunPod COMMUNITY); H1-H3 on pod 1, H4-H9 and E1-E8 on pod 2
- **base_url**: RunPod HTTP proxy (pods terminated)
- **server**: {"model": "/workspace/models/gpt-oss-120b-MXFP4.gguf", "n_ctx": 32768, "build": "b12024-ddf48f85c"}
- **reasoning_effort**: medium
- **run_at**: 2026-11-02 15:20 IST
- **total_wall_min**: 19.2
- **totals**: 8 pass / 4 partial / 5 fail
- **settings**: max_steps 40, max_tokens/turn 8192, ctx 32k, trims at 20000 tokens
- **data_note**: ILLUSTRATIVE SYNTHETIC DATA - made-up supply network, no real company data or plant names
- **seed**: 20261102
- **plants**: 6
- **intermediate_units**: 2
- **depots**: 40
- **districts**: 300
- **history_months**: 36
- **h1_raw_invoice_rows**: 26935
- **h4_invoices**: 200
- **excel_round_data**: E1-E8: sales.xlsx 150 orders x 9 cols + Products (5); sales_dups.xlsx 157 rows (7 exact dups); customers.xlsx 40 messy rows - illustrative synthetic

| test | verdict | reason | tool_calls | tool_errors | self_corrections | steps | wall_s | gen_tok_s | prompt_tok_s | stop |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | pass | pivot cells correct 30/30, regions sorted=True | 4 | 0 | 0 | 4 | 6.0 | 180.52 | 2422.36 | submitted |
| E2 | pass | formula rows 150, values ok after recalc 150/150; e.g. =IF(H2>=1.1*I2,"A",IF(H2>=I2,"B",IF(H2>=0.8*I2,"C","D"))) | 2 | 0 | 0 | 2 | 7.2 | 181.52 | 251.14 | submitted |
| E3 | pass | Category: formula rows 150, values ok after recalc 150/150; Price_per_t: formula rows 150, values ok after recalc 150/150 | 6 | 0 | 0 | 6 | 12.3 | 177.98 | 2337.42 | submitted |
| E4 | fail | formula cells ok 0/15, values ok 0/15, two-criteria SUMIFS ok=True; e.g. A2..B2 =SUMIFS(Sales!$H:$H, Sales!$D:$D, A2) | 5 | 0 | 0 | 6 | 9.5 | 178.56 | 2404.25 | final_answer |
| E5 | pass | rows 47/47, order exact=True, counts reported and printed by code {'rows_before': True, 'duplicates_removed': True, 'rows_after': True} | 4 | 0 | 0 | 5 | 5.6 | 180.05 | 2333.46 | final_answer |
| E6 | pass | CF rule H2:H151 expression ['H2<I2'] red=True covers=True logic=True | 7 | 1 | 1 | 7 | 9.3 | 179.02 | 2104.52 | submitted |
| E7 | pass | chart bar parts 1, plots Total_Revenue=True, title=True, monthly values ok=True | 5 | 0 | 0 | 5 | 8.4 | 179.14 | 2467.6 | submitted |
| E8 | partial | 40 rows; correct cells {'name': 40, 'signup': 34, 'city': 40, 'state': 40}; real date cells 40 | 5 | 0 | 0 | 5 | 8.8 | 177.93 | 2400.47 | submitted |
| H1 | fail | counts correct {'dup': True, 'bag': True, 'out': False, 'miss': False, 'total': False}; printed by code {'dup': True, 'bag': True, 'out': True, 'miss': True, 'total': True}; clean file ok False | 11 | 0 | 0 | 11 | 54.3 | 177.69 | 991.38 | submitted |
| H2 | partial | coherent=True, future district MAPE 13.751% (ref 7.457%, pass <= 10.067%), holdout reported None (ref 8.997), WLS code seen=True | 5 | 0 | 0 | 6 | 32.1 | 177.55 | 2250.85 | final_answer |
| H3 | pass | feasible=True, gap to optimum -0.0%, reported vs recomputed 0.0%, printed by code=True; problems [] | 22 | 1 | 1 | 22 | 63.2 | 151.36 | 2379.95 | submitted |
| H4 | partial | feasible=True, cost 1408200.0 vs optimum 1397400.0 (gap 0.773%), trucks 85; problems [] | 37 | 18 | 16 | 37 | 568.2 | 164.17 | 2521.45 | wall limit 540s |
| H5 | pass | flagged infeasible=True, claims plan=False, names intermediate=True, shortfall 68946.0 printed=False | 15 | 2 | 2 | 16 | 38.5 | 175.86 | 2143.54 | final_answer |
| H6 | partial | ok {'base': True, 'outage': True, 'delta': True, 'shadow': True}; delta printed=True, shadow printed=False | 16 | 3 | 3 | 16 | 84.7 | 174.41 | 2239.25 | submitted |
| H7 | fail | error % vs reference chain {'forecast_total_t': None, 'plan_cost_rs': None, 'secondary_trucks': None, 'secondary_cost_rs': None, 'end_to_end_cost_rs': None}; first stage off: forecast_total_t | 32 | 10 | 6 | 32 | 305.0 | 170.79 | 2372.85 | server error: InternalServerError: Error code: 500 - Failed to parse tool call arguments as JSON: [json.exception.parse_error.101] parse error at line 1, column 2948: syntax error while parsing value - invalid string: missing closing quote; last read: '"import pandas as pd, numpy as np, json, statsm |
| H8 | fail | asked question=False, assumptions before solving=False, only after=False | 15 | 4 | 4 | 16 | 38.0 | 175.5 | 1406.44 | final_answer |
| H9 | fail | mismatch wording=False, mentions 118000=False, capacity used (from cost)=file (118,000) | 14 | 1 | 1 | 14 | 38.7 | 176.13 | 2061.14 | submitted |

## Answers and checker details

### E1: Excel: pivot summary sheet (region x month revenue) (pass)
- answer: `{"file": "e1.xlsx", "notes": "Pivot table of Revenue by Region and Month created."}`
- details: `{"file": "e1.xlsx", "cells_correct": 30, "cells_expected": 30, "regions_sorted": true}`

### E2: Excel: nested-IF grade column as formulas (pass)
- answer: `{"file": "e2.xlsx", "notes": "Added Grade column with nested IF formulas"}`
- details: `{"file": "e2.xlsx", "rows_found": 150, "rows_expected": 150, "formula_rows": 150, "value_matches_after_recalc": 150, "sample_formula": "=IF(H2>=1.1*I2,\"A\",IF(H2>=I2,\"B\",IF(H2>=0.8*I2,\"C\",\"D\")))"}`

### E3: Excel: VLOOKUP/XLOOKUP from second sheet as formulas (pass)
- answer: `{"file": "e3.xlsx", "notes": "Added Category and Price_per_t columns with VLOOKUP formulas referencing Products sheet."}`
- details: `{"Category": {"file": "e3.xlsx", "rows_found": 150, "rows_expected": 150, "formula_rows": 150, "value_matches_after_recalc": 150, "sample_formula": "=VLOOKUP(F2,Products!$A$2:$C$6,2,FALSE)"}, "Price_per_t": {"file": "e3.xlsx", "rows_found": 150, "rows_expected": 150, "formula_rows": 150, "value_matches_after_recalc": 150, "sample_formula": "=VLOOKUP(F2,Products!$A$2:$C$6,3,FALSE)"}, "formulas_reference_Products": true}`

### E4: Excel: SUMIFS/COUNTIFS/AVERAGEIFS summary formulas (fail)
- answer: `{"file": "e4.xlsx", "notes": "Created e4.xlsx with Sales sheet and Summary sheet containing formulas as requested."}`
- details: `{"file": "e4.xlsx", "formula_cells_ok": 0, "value_cells_ok": 0, "expected": 15, "north_ppc_ok": true, "F2": "=SUMIFS(Sales!$H:$H, Sales!$D:$D, \"North\", Sales!$F:$F, \"Blend-P\")", "sample_B2": "=SUMIFS(Sales!$H:$H, Sales!$D:$D, A2)"}`

### E5: Excel: remove duplicates + filter + sort (pass)
- answer: `{"answer": {"rows_before": 157, "duplicates_removed": 7, "rows_after": 47}}`
- details: `{"rows_written": 47, "rows_expected": 47, "order_exact": true, "same_set": true, "reported": {"rows_before": 157.0, "duplicates_removed": 7.0, "rows_after": 47.0}, "reported_ok_and_printed": {"rows_before": true, "duplicates_removed": true, "rows_after": true}, "columns_ok": true}`

### E6: Excel: conditional formatting (red below target) (pass)
- answer: `{"file": "e6.xlsx", "notes": "Revenue cells turn red when below Target via dynamic conditional formatting."}`
- details: `{"file": "e6.xlsx", "cf_rules": [{"range": "H2:H151", "type": "expression", "op": null, "formula": ["H2<I2"], "colors": ["00FFC7CE", "00FFC7CE", "00FFC7CE"], "red": true, "covers_revenue_rows": true, "logic_ok": true}], "revenue_col": "H", "target_col": "I"}`

### E7: Excel: embedded bar/line chart (pass)
- answer: `{"file": "e7.xlsx", "notes": "Created Monthly sheet with total revenue per month and embedded chart"}`
- details: `{"chart_parts": ["xl/charts/chart1.xml"], "chart_type": "bar", "series_refs": ["'Monthly'!B1", "'Monthly'!$A$2:$A$7", "'Monthly'!$B$2:$B$7"], "plots_TotalRevenue": true, "title_found": true, "monthly_values_ok": true}`

### E8: Excel: text/date cleanup (TRIM, PROPER, dates, split) (partial)
- answer: `{"file": "e8.xlsx", "notes": "Cleaned customer data with proper names, parsed dates, and split city/state."}`
- details: `{"file": "e8.xlsx", "rows": 40, "correct": {"name": 40, "signup": 34, "city": 40, "state": 40}, "real_date_cells": 40}`

### H1: Data cleaning: duplicates, bag rows, outlier, missing months (fail)
- answer: `{"n_duplicate_rows_removed": 37, "n_bag_rows_converted": 58, "n_outlier_rows": 221, "n_missing_district_months": 198, "clean_total_tonnes": 18270329.2, "issues": ["37 duplicate rows removed", "58 rows with bag units converted to tonnes", "221 outlier rows removed (3 sigma rule)", "198 district-month combos missing and imputed"]}`
- details: `{"got": {"dup": 37.0, "bag": 58.0, "out": 221.0, "miss": 198.0, "total": 18270329.2}, "expected": {"dup": 37, "bag": 58, "out": 1, "miss": 23, "total": 19245730.0}, "correct": {"dup": true, "bag": true, "out": false, "miss": false, "total": false}, "printed_by_code": {"dup": true, "bag": true, "out": true, "miss": true, "total": true}, "python_used": true, "clean_file": {"rows": 10800, "nan": 0, "share_cells_matching_truth": 0.9802}, "clean_file_ok": false}`

### H2: Forecast 300 districts x 3 months + WLS hierarchy reconciliation (partial)
- answer: `The forecasts were generated with a LightGBM regression model for each district, then aggregated to plants and the overall total.  A MinT‑diagonal reconciliation (weighted least squares using in‑sample residual variances) was applied so that district forecasts sum exactly to their plant forecasts and plant forecasts sum to the total.

**Method:** LightGBM regression with MinT diagonal reconciliation  
**Hold‑out district‑level MAPE (%):** 10.51 %  
**Reconciled total forecasts (tonnes) for 2026‑`
- details: `{"python_used": true, "rows": {"district": 900, "plant": 18, "total": 3}, "coherent": true, "max_plant_err_t": 0.0, "max_total_err_t": 0.0, "future_district_mape_pct": 13.751, "ref_future_mape_pct": 7.457, "pass_band_pct": 10.067, "partial_band_pct": 14.914, "holdout_reported": null, "ref_holdout_mape_pct": 8.997, "holdout_printed_by_code": false, "wls_code_seen": true, "method": null}`

### H3: 3-month production / intermediate-rake / inventory MILP (pass)
- answer: `{"total_cost_rs": 4750925789.657779, "solver_status": "Optimal", "mip_gap": null, "total_rakes": 104.00000000000001}`
- details: `{"python_used": true, "reference_optimum_rs": 4750925790.0, "feasible": true, "problems": [], "recomputed_cost_rs": 4750925790.0, "reported_cost_rs": 4750925789.657779, "gap_to_optimum_pct": -0.0, "reported_vs_recomputed_pct": 0.0, "cost_printed_by_code": true}`

### H4: Club 200 invoices onto trucks (windows, routes, districts) MILP (partial)
- answer: ``
- details: `{"python_used": true, "reference_optimum_rs": 1397400.0, "reference_trucks": 85, "feasible": true, "problems": [], "recomputed_cost_rs": 1408200.0, "trucks": 85, "reported_cost_rs": null, "gap_pct": 0.773, "cost_printed_by_code": false}`

### H5: Trap: demand surge infeasible (intermediate-bound) (pass)
- answer: `{"status": "Infeasible", "total_cost_rs": null, "explanation": "The network cannot satisfy the product demand because the total intermediate required (0.72\u202f\u00d7\u202f2,169,279\u202ft\u202f\u2248\u202f1,561,881\u202ft) exceeds the combined monthly intermediate supply from all stage-1 lines (340,000\u202ft/month\u202f\u00d7\u202f3\u202f=\u202f1,020,000\u202ft) plus the two intermediate units (85,000\u202ft + 75,000\u202ft = 160,000\u202ft/month\u202f\u00d7\u202f3\u202f=\u202f480,000\u202ft). The total available cl`
- details: `{"status": "Infeasible", "flagged_infeasible": true, "claims_plan": false, "reported_cost": null, "mentions_intermediate": true, "explanation": "The network cannot satisfy the product demand because the total intermediate required (0.72\u202f\u00d7\u202f2,169,279\u202ft\u202f\u2248\u202f1,561,881\u202ft) exceeds the combined monthly intermediate supply from all stage-1 lines (340,000\u202ft/month\u202f\u00d7\u202f3\u202f=\u202f1,020,000\u202ft) plus the two intermediate units (85,000\u202ft + 75,000\u202ft = 160,000\u202ft/month\u202f\u00d7\u202f3\u202f=\u202f480,000\u202ft). The total available intermediate over the three\u2011month horizon is 1,500,000\u202ft, leaving a shortfall of about 61,8", "ref_shortfall_t": 68946.0, "shortfall_printed_by_code": false, "python_used": true}`

### H6: What-if: mid-month plant outage, delta + shadow prices (partial)
- answer: `{"base_cost_rs": 4723812781.842002, "outage_cost_rs": 4729991130.950792, "delta_rs": 6178349.108790398, "shadow_price_rs_per_t": 71.776, "lost_capacity_t": 59000, "first_order_estimate_rs": 4234784.0, "explanation": "The shadow price of the P5_Plover finishing capacity in Dec 2026 is -71.776 Rs per tonne (negative because the constraint is a \u2264 bound). Interpreted as a saving, each extra tonne of capacity would reduce total cost by about 71.8 Rs. The outage halves the capacity, losing 59,000 `
- details: `{"got": {"base": 4723812781.842002, "outage": 4729991130.950792, "delta": 6178349.108790398, "shadow": 71.776}, "ok": {"base": true, "outage": true, "delta": true, "shadow": true}, "reference": {"base_cost_rs": 4723812782.0, "outage_cost_rs": 4729991135.0, "delta_rs": 6178353.0, "base_shadow_saving_rs_per_t": 71.776, "lost_capacity_t": 59000.0, "dual_x_lost_rs": 4234784.0}, "delta_printed_by_code": true, "shadow_printed_by_code": false, "python_used": true, "replan_file_feasible": true, "replan_file_cost": 4729991131.0, "replan_problems": []}`

### H7: Chain: forecast -> plan MILP -> secondary trucks, end-to-end cost (fail)
- answer: ``
- details: `{"got": {"forecast_total_t": null, "plan_cost_rs": null, "secondary_trucks": null, "secondary_cost_rs": null, "end_to_end_cost_rs": null}, "reference": {"forecast_total_t": 1883982.0, "plan_cost_rs": 4746592015.0, "secondary_trucks": 63244, "secondary_cost_rs": 371657724.0, "end_to_end_cost_rs": 5118249739.0}, "err_pct": {"forecast_total_t": null, "plan_cost_rs": null, "secondary_trucks": null, "secondary_cost_rs": null, "end_to_end_cost_rs": null}, "e2e_printed_by_code": false, "python_used": true, "first_stage_off": "forecast_total_t"}`

### H8: Vague ask: 'Cut freight cost.' (fail)
- answer: `{"total_freight_cost_rs": 1825245419.5, "suggested_cut_percentage": 5, "estimated_savings_rs": 91262270.975}`
- details: `{"asked_clarifying_question": false, "assumptions_stated_before_solving": false, "assumptions_only_after_solving": false, "assumption_only_in_code_comments": false, "first_solver_step": 10, "stop": "final_answer", "final_text_start": "{\n  \"total_freight_cost_rs\": 1825245419.5,\n  \"suggested_cut_percentage\": 5,\n  \"estimated_savings_rs\": 91262270.975\n}"}`

### H9: Prompt contradicts data file (P5 capacity) (fail)
- answer: `{"total_cost_rs": 4723812781.842, "notes": "LP solved (CBC) for illustrative synthetic network. All depot demand met, plant capacities respected, intermediate balance satisfied, inventories within limits and safety stock met. Rake count set to 0 as instructed."}`
- details: `{"flags_mismatch_words": false, "mentions_file_value_118000": false, "capacity_used_by_cost": "file (118,000)", "reported_cost": 4723812781.842, "ref_costs": {"file": 4723812782.0, "prompt": 4721914820.0}, "notes": "LP solved (CBC) for illustrative synthetic network. All depot demand met, plant capacities respected, intermediate balance satisfied, inventories within limits and safety stock met. Rake count set to 0 as instructed."}`

