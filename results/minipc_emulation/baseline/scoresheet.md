# Tough pack scoresheet: gpt-oss-120b MXFP4, mini-PC emulation (1x RTX PRO 6000 Blackwell Workstation Edition, VRAM capped to 34 GB budget, RAM <=64 GB, -t 10) baseline

- **label**: gpt-oss-120b MXFP4, mini-PC emulation (1x RTX PRO 6000 Blackwell Workstation Edition, VRAM capped to 34 GB budget, RAM <=64 GB, -t 10) baseline
- **mode**: baseline
- **base_url**: https://<POD_ID>-8000.proxy.runpod.net/v1
- **server**: {"model": "/workspace/models/gpt-oss-120b-MXFP4.gguf", "n_ctx": 65536, "build": "b12024-ddf48f85c"}
- **reasoning_effort**: medium
- **run_at**: 2026-11-02 20:09 IST
- **total_wall_min**: 57.1
- **totals**: 2 pass / 0 partial / 5 fail
- **settings**: max_steps 40, max_tokens/turn 8192, ctx 65536, trims at 20000 tokens
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
| H1 | fail | counts correct {'dup': True, 'bag': True, 'out': False, 'miss': False, 'total': False}; printed by code {'dup': True, 'bag': True, 'out': True, 'miss': True, 'total': True}; clean file ok False | 9 | 0 | 0 | 9 | 57.9 | 66.87 | 336.02 | submitted |
| H2 | fail | forecast_reconciled.csv missing or wrong columns | 6 | 0 | 0 | 6 | 66.5 | 69.33 | 460.95 | server error: APIError: The model produced output that does not match the expected peg-native format |
| H3 | pass | feasible=True, gap to optimum -0.0%, reported vs recomputed 0.0%, printed by code=True; problems [] | 13 | 2 | 2 | 13 | 122.2 | 66.27 | 582.02 | submitted |
| H4 | fail | feasible=False, cost 52000.0 vs optimum 1397400.0 (gap -96.279%), trucks 3; problems ["197 invoices not loaded e.g. ['OB001', 'OB002', 'OB003']"] | 24 | 10 | 9 | 24 | 1598.1 | 65.56 | 1208.31 | wall limit 1355s |
| H5 | fail | flagged infeasible=False, claims plan=False, names intermediate=False, shortfall 68946.0 printed=False | 40 | 27 | 26 | 40 | 991.0 | 65.03 | 1289.67 | max_steps 40 |
| H6 | fail | ok {'base': False, 'outage': False, 'delta': False, 'shadow': False}; delta printed=False, shadow printed=False | 18 | 3 | 3 | 18 | 222.7 | 66.62 | 568.41 | server error: APIError: The model produced output that does not match the expected peg-native format |
| H7 | pass | error % vs reference chain {'forecast_total_t': 0.0, 'plan_cost_rs': 0.0, 'secondary_trucks': 0.0, 'secondary_cost_rs': 0.0, 'end_to_end_cost_rs': 0.0}; first stage off: None | 24 | 5 | 5 | 24 | 365.9 | 66.56 | 714.32 | submitted |

## Answers and checker details

### H1: Data cleaning: duplicates, bag rows, outlier, missing months (fail)
- answer: `{"n_duplicate_rows_removed": 37, "n_bag_rows_converted": 58, "n_outlier_rows": 444, "n_missing_district_months": 352, "clean_total_tonnes": 17597192.0, "issues": ["Removed 37 duplicate invoice_id rows", "Converted 58 bag rows to tonnes (0.05 t per bag)", "Removed 444 outlier rows based on 3*IQR rule", "Imputed 352 missing district-month combos"]}`
- details: `{"got": {"dup": 37.0, "bag": 58.0, "out": 444.0, "miss": 352.0, "total": 17597192.0}, "expected": {"dup": 37, "bag": 58, "out": 1, "miss": 23, "total": 19245730.0}, "correct": {"dup": true, "bag": true, "out": false, "miss": false, "total": false}, "printed_by_code": {"dup": true, "bag": true, "out": true, "miss": true, "total": true}, "python_used": true, "clean_file": {"rows": 10800, "nan": 0, "share_cells_matching_truth": 0.9601}, "clean_file_ok": false}`

### H2: Forecast 300 districts x 3 months + WLS hierarchy reconciliation (fail)
- answer: ``
- details: `{"python_used": true, "file": "forecast_reconciled.csv missing or wrong columns"}`

### H3: 3-month production / intermediate-rake / inventory MILP (pass)
- answer: `{"total_cost_rs": 4750925786.332661, "solver_status": "Optimal", "mip_gap": 0, "total_rakes": 104}`
- details: `{"python_used": true, "reference_optimum_rs": 4750925790.0, "feasible": true, "problems": [], "recomputed_cost_rs": 4750925786.0, "reported_cost_rs": 4750925786.332661, "gap_to_optimum_pct": -0.0, "reported_vs_recomputed_pct": 0.0, "cost_printed_by_code": true}`

### H4: Club 200 invoices onto trucks (windows, routes, districts) MILP (fail)
- answer: ``
- details: `{"python_used": true, "reference_optimum_rs": 1397400.0, "reference_trucks": 85, "feasible": false, "problems": ["197 invoices not loaded e.g. ['OB001', 'OB002', 'OB003']"], "recomputed_cost_rs": 52000.0, "trucks": 3, "reported_cost_rs": null, "gap_pct": -96.279, "cost_printed_by_code": false}`

### H5: Trap: demand surge infeasible (intermediate-bound) (fail)
- answer: ``
- details: `{"status": "", "flagged_infeasible": false, "claims_plan": false, "reported_cost": null, "mentions_intermediate": false, "explanation": "", "ref_shortfall_t": 68946.0, "shortfall_printed_by_code": false, "python_used": true}`

### H6: What-if: mid-month plant outage, delta + shadow prices (fail)
- answer: ``
- details: `{"got": {"base": null, "outage": null, "delta": null, "shadow": null}, "ok": {"base": false, "outage": false, "delta": false, "shadow": false}, "reference": {"base_cost_rs": 4723812782.0, "outage_cost_rs": 4729991135.0, "delta_rs": 6178353.0, "base_shadow_saving_rs_per_t": 71.776, "lost_capacity_t": 59000.0, "dual_x_lost_rs": 4234784.0}, "delta_printed_by_code": false, "shadow_printed_by_code": false, "python_used": true, "replan_file_feasible": true, "replan_file_cost": 4729991131.0, "replan_problems": []}`

### H7: Chain: forecast -> plan MILP -> secondary trucks, end-to-end cost (pass)
- answer: `{"forecast_total_t": 1883982.022606874, "plan_cost_rs": 4746592012.639123, "secondary_trucks": 63244, "secondary_cost_rs": 371657724.0, "end_to_end_cost_rs": 5118249736.639123}`
- details: `{"got": {"forecast_total_t": 1883982.022606874, "plan_cost_rs": 4746592012.639123, "secondary_trucks": 63244.0, "secondary_cost_rs": 371657724.0, "end_to_end_cost_rs": 5118249736.639123}, "reference": {"forecast_total_t": 1883982.0, "plan_cost_rs": 4746592015.0, "secondary_trucks": 63244, "secondary_cost_rs": 371657724.0, "end_to_end_cost_rs": 5118249739.0}, "err_pct": {"forecast_total_t": 0.0, "plan_cost_rs": 0.0, "secondary_trucks": 0.0, "secondary_cost_rs": 0.0, "end_to_end_cost_rs": 0.0}, "e2e_printed_by_code": true, "python_used": true, "first_stage_off": null, "plan_files_present": true}`

