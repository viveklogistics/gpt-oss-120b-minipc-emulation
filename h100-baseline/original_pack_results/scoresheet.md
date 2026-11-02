# Scoresheet: gpt-oss-120b H100 NVL MXFP4 (A100 unavailable)

- **label**: gpt-oss-120b H100 NVL MXFP4 (A100 unavailable)
- **base_url**: https://<POD_ID>-8000.proxy.runpod.net/v1
- **server**: {"model": "gpt-oss-120b-MXFP4.gguf", "n_ctx": 32768, "build": "b12024-ddf48f85c"}
- **reasoning_effort**: medium
- **run_at**: 2026-11-02 13:37 IST
- **total_wall_min**: 3.5
- **totals**: 5 pass / 0 partial / 0 fail
- **gmktec_note**: GMKtec EVO-X2 tok/s is an ESTIMATE = measured H100 NVL tok/s / 15.2 (memory bandwidth ratio ~3.9 TB/s vs ~256 GB/s, not measured on the device)
- **data_note**: All T2-T5 data is synthetic/illustrative. T1 used public map data only and is not published.

| test | verdict | tool_calls | tool_errors | bad_json_calls | wall_s | gen_tok_s | prompt_tok_s | est_gmktec_gen_tok_s (ESTIMATE = gen_tok_s / 15.2) | stop | result |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | pass | 13 | 0 | 0 | 42.0 | 176.0 | 1786.83 | 11.6 | final_answer | [withheld: T1 was a geo lookup on public map data about a real site; it is not in the public kit] |
| T2 | pass | 3 | 2 | 0 | 18.4 | 178.48 | 2267.99 | 11.7 | final_answer | {"mape_sarimax": 2.7718, "mape_poisson": 2.1707, "mape_blend": 2.1664, "forecast_blend": [3256.1327, 3183.1023, 3395.8562, 3767.925, 3975.448, 4501.6589, 3997.5 |
| T3 | pass | 8 | 2 | 0 | 86.2 | 176.62 | 2009.67 | 11.6 | submitted | {"total_cost_rs": 118500, "trucks_used": 6, "trucks": [["INV01", "INV02"], ["INV04", "INV07"], ["INV10", "INV11"], ["INV05", "INV06"], ["INV03", "INV08", "INV12 |
| T4 | pass | 9 | 0 | 0 | 28.2 | 177.57 | 1719.64 | 11.7 | submitted | {"x": [2.0, 1.0, 0.0], "lambda": [1.0, 2.0, 0.0], "mu": [0.0, 0.0, 3.0], "objective": -16.5, "kkt_max_residual": 0.0, "active_constraints": [0, 1], "active_boun |
| T5 | pass | 9 | 1 | 0 | 32.7 | 176.73 | 2130.32 | 11.6 | submitted | {"total_cost_rs": 110230000, "flows": {"P1_Ashford->D1_Eastport": 8000, "P1_Ashford->D3_Glenrock": 22000, "P1_Ashford->D6_Juniper": 12000, "P2_Brindle->D1 |

## Checker details

- **T1** (pass): [withheld: T1 was a geo lookup on public map data about a real site; it is not in the public kit]
- **T2** (pass): `{"got": {"mape_sarimax": 2.7718, "mape_poisson": 2.1707, "mape_blend": 2.1664}, "reference": {"mape_sarimax": 2.772, "mape_poisson": 2.171, "mape_blend": 2.166}, "abs_err_pp": {"mape_sarimax": 0.0, "mape_poisson": 0.0, "mape_blend": 0.0}, "python_used": true, "blend_printed_by_code": true}`
- **T3** (pass): `{"reported_cost": 118500.0, "recomputed_cost": 118500, "feasible": true, "problems": [], "reference_optimum": 118500, "reference_trucks": 6, "python_used": true, "cost_printed_by_code": true}`
- **T4** (pass): `{"x": [2.0, 1.0, 0.0], "lambda": [1.0, 2.0, 0.0], "mu": [0.0, 0.0, 3.0], "x_ok": true, "lambda_ok": true, "mu_ok": true, "objective_ok": true, "residual_reported": 0.0, "residual_ok": true, "kkt_terms_present": {"stationarity": true, "primal": true, "dual": true, "complementary": true}, "active_sets_ok": true, "reference": {"x": [2.0, 1.0, 0.0], "lambda_Ax_le_b": [1.0, 2.0, 0.0], "mu_x_ge_0": [0.0, 0.0, 3.0], "objective": -16.5, "active_constraints": [0, 1], "active_bounds": [2]}, "python_used": true, "objective_printed_by_code": true}`
- **T5** (pass): `{"total_cost": 110230000.0, "cost_ok": true, "district_duals_correct": "6/6", "plant_duals_correct": "4/4", "whatif_new_cost": 109730000.0, "whatif_ok": true, "district_detail": {"D1_Eastport": [1070.0, 1070.0, true], "D2_Fairview": [870.0, 870.0, true], "D3_Glenrock": [1460.0, 1460.0, true], "D4_Harlow": [920.0, 920.0, true], "D5_Ironvale": [840.0, 840.0, true], "D6_Juniper": [1270.0, 1270.0, true]}, "plant_detail": {"P1_Ashford": [250.0, 250.0, true], "P2_Brindle": [110.0, 110.0, true], "P3_Calder": [0.0, 0.0, true], "P4_Dunmore": [230.0, 230.0, true]}, "reference_cost": 110230000.0, "reference_whatif": 109730000.0, "python_used": true, "cost_printed_by_code": true}`
