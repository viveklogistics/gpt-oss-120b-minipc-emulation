"""E1-E8: general Excel skills on small ILLUSTRATIVE SYNTHETIC sales / dispatch sheets (made-up company).
Checkers open the saved .xlsx: formulas must be present where asked, values are checked after a LibreOffice headless
recalculation against a pandas reference, and the conditional-formatting rule and chart objects must exist."""
import json, re, shutil, subprocess, tempfile, zipfile
from datetime import datetime, date
from pathlib import Path
import numpy as np, pandas as pd, openpyxl
from harness_tough import PYTHON_TOOL, SUBMIT_TOOL, FILE_TOOLS, make_file_funcs, make_python_exec
HERE = Path(__file__).resolve().parent; XD = HERE / "data" / "excel"
NOTE = "ILLUSTRATIVE SYNTHETIC DATA - made-up company"
REGIONS = ["Central", "East", "North", "South", "West"]; PRODUCTS = ["Std 53", "Blend-P", "Blend-S", "Composite", "Bulk Std"]
MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

def gen():
    rng = np.random.default_rng(20261102); XD.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(150):
        m = MONTHS[i % 6]; d = date(int(m[:4]), int(m[5:]), int(rng.integers(1, 28)))
        p = PRODUCTS[int(rng.integers(0, 5))]; q = int(rng.integers(5, 60)); price = {"Std 53": 5600, "Blend-P": 5200, "Blend-S": 5000, "Composite": 4900, "Bulk Std": 4700}[p]
        rev = int(round(q * price * float(rng.uniform(0.9, 1.1)), -1)); tgt = int(round(q * price * float(rng.uniform(0.85, 1.2)), -2))
        rows.append(dict(OrderID=f"SO{1001 + i}", OrderDate=datetime(d.year, d.month, d.day), Month=m, Region=REGIONS[int(rng.integers(0, 5))],
                         Depot=f"D{int(rng.integers(1, 13)):02d}", Product=p, Qty_t=q, Revenue=rev, Target=tgt))
    S = pd.DataFrame(rows)
    P = pd.DataFrame({"Product": PRODUCTS, "Category": ["Grey bagged", "Blended bagged", "Blended bagged", "Blended bagged", "Bulk"],
                      "Price_per_t": [5600, 5200, 5000, 4900, 4700]})
    with pd.ExcelWriter(XD / "sales.xlsx") as xw:
        S.to_excel(xw, sheet_name="Sales", index=False); P.to_excel(xw, sheet_name="Products", index=False)
        pd.DataFrame({"note": [NOTE]}).to_excel(xw, sheet_name="README", index=False)
    dup_idx = [3, 17, 17, 40, 88, 121, 149]                       # 7 duplicate rows (SO1018 twice)
    SD = pd.concat([S, S.iloc[dup_idx]]).sample(frac=1, random_state=7).reset_index(drop=True)
    with pd.ExcelWriter(XD / "sales_dups.xlsx") as xw:
        SD.to_excel(xw, sheet_name="Sales", index=False); pd.DataFrame({"note": [NOTE]}).to_excel(xw, sheet_name="README", index=False)
    first = ["ramesh", "anita", "SURESH", "kavya", "imran", "meera", "joseph", "priya", "arjun", "fatima", "deepak", "lakshmi"]
    last = ["kumar", "SHARMA", "iyer", "khan", "das", "nair", "PATIL", "reddy", "singh", "joshi"]
    # fictional towns and provinces (no real places); same casing/spacing mess as before, same number of random draws
    cities = [("tamberly", "westmark"), ("ORVANTE", "Westmark"), ("quillon", "rosmere"), ("vessaby", "NORTH ELDA"),
              ("marrowind", "calder coast"), ("zerinth", "dunvale"), ("pellacombe", "ashmark"), ("korvaine", "brightfen")]
    cust, clean = [], []
    for i in range(40):
        f, l = first[int(rng.integers(0, 12))], last[int(rng.integers(0, 10))]; c, s = cities[int(rng.integers(0, 8))]
        d = date(2025, 1, 1) + pd.Timedelta(days=int(rng.integers(0, 600)))
        fmt = i % 3; ds = d.strftime("%Y-%m-%d") if fmt == 0 else d.strftime("%d/%m/%Y") if fmt == 1 else f"{d.day} {d.strftime('%b %Y')}"
        sp = " " * int(rng.integers(1, 3))
        cust.append(dict(CustID=f"C{201 + i}", CustName=f"{' ' * int(rng.integers(0, 3))}{f}{sp}{l}{' ' * int(rng.integers(0, 3))}",
                         SignupDate=ds, Location=f" {c}{' ' * int(rng.integers(0, 3))}-{' ' * int(rng.integers(0, 3))}{s} "))
        clean.append(dict(CustID=f"C{201 + i}", Name=f"{f.title()} {l.title()}", Signup=d.isoformat(), City=c.title(), State=s.title()))
    with pd.ExcelWriter(XD / "customers.xlsx") as xw:
        pd.DataFrame(cust).to_excel(xw, sheet_name="Customers", index=False); pd.DataFrame({"note": [NOTE]}).to_excel(xw, sheet_name="README", index=False)
    # ---- reference answers
    piv = S.pivot_table(index="Region", columns="Month", values="Revenue", aggfunc="sum").sort_index()
    r = S.Revenue / S.Target
    grade = np.where(r >= 1.1, "A", np.where(r >= 1.0, "B", np.where(r >= 0.8, "C", "D")))
    summ = S.groupby("Region").agg(Total_Revenue=("Revenue", "sum"), Orders=("OrderID", "count"), Avg_Qty=("Qty_t", "mean")).sort_index()
    nd = SD.drop_duplicates(); e5 = nd[(nd.Qty_t >= 20) & nd.Region.isin(["North", "West"])].sort_values(["Revenue", "OrderID"], ascending=[False, True])
    ref = {"note": NOTE, "pivot": {k: {m: float(v) for m, v in row.items()} for k, row in piv.iterrows()},
           "grade": dict(zip(S.OrderID, grade.tolist())), "category": dict(zip(S.OrderID, S.Product.map(dict(zip(P.Product, P.Category))))),
           "price": dict(zip(S.OrderID, S.Product.map(dict(zip(P.Product, P.Price_per_t))).astype(float))),
           "summary": {k: {c: float(v) for c, v in row.items()} for k, row in summ.iterrows()},
           "north_ppc": float(S[(S.Region == "North") & (S.Product == "Blend-P")].Revenue.sum()),
           "e5": {"rows_before": len(SD), "duplicates_removed": len(SD) - len(nd), "rows_after": len(e5), "order": e5.OrderID.tolist()},
           "monthly": {m: float(v) for m, v in S.groupby("Month").Revenue.sum().items()}, "customers": clean, "n_sales": len(S)}
    (XD / "reference_excel.json").write_text(json.dumps(ref, indent=1))
    return ref

if not (XD / "reference_excel.json").exists(): gen()
EREF = json.loads((XD / "reference_excel.json").read_text())

# ------------------------------------------------------------------ helpers
def recalc(path):
    """LibreOffice headless round-trip -> workbook with recalculated cached values (data_only)."""
    td = Path(tempfile.mkdtemp()); src = td / "in.xlsx"; shutil.copy(path, src)
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(td / "out"), str(src)],
                   capture_output=True, timeout=120, env={"HOME": str(td), "PATH": "/usr/bin:/bin"})
    out = td / "out" / "in.xlsx"
    return openpyxl.load_workbook(out, data_only=True) if out.exists() else None

def _hdr(ws):
    return {str(c.value).strip().lower(): c.column for c in ws[1] if c.value is not None}

def _sheet(wb, name):
    for s in wb.sheetnames:
        if s.strip().lower() == name.lower(): return wb[s]
    return None

def _rows_by_id(ws, idcol="orderid"):
    h = _hdr(ws); c = h.get(idcol)
    if not c: return h, {}
    return h, {ws.cell(r, c).value: r for r in range(2, ws.max_row + 1) if ws.cell(r, c).value}

def _isf(v): return isinstance(v, str) and v.startswith("=")
def _close(a, b, tol=0.51):
    try: return abs(float(a) - float(b)) <= tol
    except Exception: return False
def _load(wd, name):
    p = wd / name
    if not p.exists(): return None, None, {"file": f"{name} missing"}
    try: return openpyxl.load_workbook(p), recalc(p), {"file": name}
    except Exception as e: return None, None, {"file": f"{name} unreadable: {type(e).__name__}: {e}"}

def _formula_col(log, wd, fname, sheet, colname, pattern, refmap, cmp):
    wb, wv, det = _load(wd, fname)
    if wb is None: return "fail", det
    ws, vs = _sheet(wb, sheet), (_sheet(wv, sheet) if wv else None)
    if ws is None: return "fail", {**det, "error": f"sheet {sheet} missing"}
    h, ids = _rows_by_id(ws); c = h.get(colname.lower())
    if not c: return "fail", {**det, "error": f"column {colname} missing", "headers": list(h)}
    nf = sum(_isf(ws.cell(r, c).value) and re.search(pattern, ws.cell(r, c).value, re.I) is not None for r in ids.values())
    ok = sum(cmp(vs.cell(r, c).value, refmap.get(i)) for i, r in ids.items()) if vs else 0
    n = len(refmap); det.update({"rows_found": len(ids), "rows_expected": n, "formula_rows": nf, "value_matches_after_recalc": ok,
                                 "sample_formula": next((ws.cell(r, c).value for r in ids.values()), None)})
    if len(ids) == n and nf == n and ok == n: return "pass", det
    if ok >= 0.9 * n: return "partial", {**det, "why": "values right but formulas missing/incomplete" if nf < n else "a few values wrong"}
    return "fail", det

# ------------------------------------------------------------------ prompts
COMMON = (" The files are ILLUSTRATIVE SYNTHETIC DATA. Use python_exec with openpyxl and/or pandas to read and write .xlsx files "
          "in the working directory. When done, call submit_answer with {\"file\": <name>, \"notes\": <one line>}")
E1_USER = ("sales.xlsx (sheet Sales) has one row per order: OrderID, OrderDate, Month, Region, Depot, Product, Qty_t, Revenue, Target. "
           "Build a pivot-table summary as a sheet: create e1.xlsx with a sheet named 'Pivot' where A1 is 'Region', column A lists the "
           "regions A-Z from row 2, row 1 from column B lists the months ascending, and each cell is the sum of Revenue for that region "
           "and month (static values or formulas are both fine; no blank cells)." + COMMON)
E2_USER = ("sales.xlsx (sheet Sales): add a column with header 'Grade' right after the last column, for every order row, written as a "
           "real Excel nested-IF FORMULA (not a pasted value): 'A' if Revenue >= 1.1*Target, 'B' if Revenue >= Target, 'C' if "
           "Revenue >= 0.8*Target, else 'D'. Keep all other sheets and data. Save as e2.xlsx." + COMMON)
E3_USER = ("sales.xlsx has sheets Sales and Products (Product, Category, Price_per_t). In sheet Sales add two columns 'Category' and "
           "'Price_per_t' filled for every order row with lookup FORMULAS (VLOOKUP, XLOOKUP or INDEX/MATCH) into the Products sheet "
           "by Product - not pasted values. Keep the Products sheet. Save as e3.xlsx." + COMMON)
E4_USER = ("sales.xlsx (sheet Sales). Create e4.xlsx that keeps the Sales sheet and adds a sheet 'Summary': A1:D1 headers Region, "
           "Total_Revenue, Orders, Avg_Qty; then one row for each distinct region name that appears in the Sales sheet's Region column, sorted alphabetically (A to Z). Column B must be a SUMIFS formula of Revenue, C a COUNTIFS "
           "formula, D an AVERAGEIFS formula of Qty_t, all referencing the Sales sheet. Also put 'North_PPC_Revenue' in F1 and in F2 "
           "a SUMIFS formula with two criteria: Region = North and Product = Blend-P." + COMMON)
E5_USER = ("sales_dups.xlsx (sheet Sales) contains some exact duplicate rows. Remove exact duplicates (keep the first), then filter to "
           "rows with Qty_t >= 20 and Region North or West, then sort by Revenue descending (ties by OrderID ascending). Write the "
           "result with the same columns to sheet 'Clean' of e5.xlsx. In submit_answer also give rows_before, duplicates_removed "
           "and rows_after, as printed by your code.")
E6_USER = ("sales.xlsx (sheet Sales). Save a copy as e6.xlsx where the Revenue column (all order rows) has a real Excel CONDITIONAL "
           "FORMATTING rule that shows a cell with a red fill when that row's Revenue is below its Target (not a static fill: the "
           "rule must update if numbers change)." + COMMON)
E7_USER = ("sales.xlsx (sheet Sales). Create e7.xlsx with a sheet 'Monthly' holding Month (A) and Total_Revenue (B) for the 6 months "
           "ascending from row 2 (header in row 1), and embed a native Excel bar or line chart titled 'Monthly Revenue' on that "
           "sheet that plots the Total_Revenue range." + COMMON)
E8_USER = ("customers.xlsx (sheet Customers): CustID, CustName (stray spaces, mixed case), SignupDate (TEXT in mixed formats: "
           "YYYY-MM-DD, DD/MM/YYYY (day first) and 'D Mon YYYY'), Location ('city - state' with messy spaces and case). Create "
           "e8.xlsx with sheet 'Clean' and columns CustID, Name (trimmed, single spaces, Proper Case), Signup (a real Excel DATE "
           "cell, not text), City and State (split from Location, trimmed, Proper Case). Keep the original order." + COMMON)

# ------------------------------------------------------------------ checkers
def e1_check(log, wd):
    wb, wv, det = _load(wd, "e1.xlsx")
    if wb is None: return "fail", det
    ws = _sheet(wv or wb, "Pivot")
    if ws is None: return "fail", {**det, "error": "sheet Pivot missing"}
    months = {str(ws.cell(1, c).value).strip()[:7]: c for c in range(2, ws.max_column + 1) if ws.cell(1, c).value is not None}
    regs = {str(ws.cell(r, 1).value).strip(): r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value is not None}
    good = tot = 0
    for rg, mm in EREF["pivot"].items():
        for m, v in mm.items():
            tot += 1; good += bool(rg in regs and m in months and _close(ws.cell(regs[rg], months[m]).value, v))
    order_ok = [k for k in regs if k in EREF["pivot"]] == sorted(EREF["pivot"])
    det.update({"cells_correct": good, "cells_expected": tot, "regions_sorted": order_ok})
    if good == tot: return "pass", det
    return ("partial" if good >= tot * 0.6 else "fail"), det

def e2_check(log, wd):
    return _formula_col(log, wd, "e2.xlsx", "Sales", "Grade", r"\bIF\(", EREF["grade"], lambda a, b: str(a).strip() == b)

def e3_check(log, wd):
    v1, d1 = _formula_col(log, wd, "e3.xlsx", "Sales", "Category", r"LOOKUP\(|MATCH\(", EREF["category"], lambda a, b: str(a).strip() == b)
    v2, d2 = _formula_col(log, wd, "e3.xlsx", "Sales", "Price_per_t", r"LOOKUP\(|MATCH\(", EREF["price"], _close)
    ref_products = all("products" in str(d.get("sample_formula", "")).lower() for d in (d1, d2))
    det = {"Category": d1, "Price_per_t": d2, "formulas_reference_Products": ref_products}
    if v1 == v2 == "pass" and ref_products: return "pass", det
    return ("partial" if "fail" not in (v1, v2) or "pass" in (v1, v2) else "fail"), det

def e4_check(log, wd):
    wb, wv, det = _load(wd, "e4.xlsx")
    if wb is None: return "fail", det
    ws, vs = _sheet(wb, "Summary"), (_sheet(wv, "Summary") if wv else None)
    if ws is None or vs is None: return "fail", {**det, "error": "sheet Summary missing (or recalc failed)"}
    regs = {str(ws.cell(r, 1).value).strip(): r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value}
    fok = vok = 0; n = 0
    for rg, ref in EREF["summary"].items():
        r = regs.get(rg)
        for col, fn, key in ((2, "SUMIFS", "Total_Revenue"), (3, "COUNTIFS", "Orders"), (4, "AVERAGEIFS", "Avg_Qty")):
            n += 1
            if not r: continue
            f = ws.cell(r, col).value; fok += _isf(f) and fn in f.upper(); vok += _close(vs.cell(r, col).value, ref[key], 0.011)
    f2 = ws["F2"].value; np_ok = _isf(f2) and "SUMIFS" in f2.upper() and f2.upper().count(",") >= 4 and _close(vs["F2"].value, EREF["north_ppc"])
    det.update({"formula_cells_ok": fok, "value_cells_ok": vok, "expected": n, "north_ppc_ok": np_ok, "F2": f2,
                "sample_B2": ws["B2"].value})
    if fok == vok == n and np_ok: return "pass", det
    return ("partial" if vok >= n * 0.6 else "fail"), det

def e5_check(log, wd):
    from tests_tough import _get, _num, _grounded
    p = wd / "e5.xlsx"; R = EREF["e5"]; a = log.get("answer") or {}
    if not p.exists(): return "fail", {"file": "e5.xlsx missing"}
    try: df = pd.read_excel(p, sheet_name="Clean")
    except Exception as e: return "fail", {"error": f"sheet Clean unreadable: {e}"}
    got = df["OrderID"].astype(str).tolist() if "OrderID" in df else []
    nums = {k: _num(_get(a, k)) for k in ("rows_before", "duplicates_removed", "rows_after")}
    nums_ok = {k: nums[k] == R[k] and _grounded(log, nums[k]) for k in nums}
    det = {"rows_written": len(got), "rows_expected": len(R["order"]), "order_exact": got == R["order"], "same_set": set(got) == set(R["order"]),
           "reported": nums, "reported_ok_and_printed": nums_ok, "columns_ok": list(df.columns)[:9] == ["OrderID", "OrderDate", "Month", "Region", "Depot", "Product", "Qty_t", "Revenue", "Target"]}
    if got == R["order"] and all(nums_ok.values()): return "pass", det
    return ("partial" if det["same_set"] or got == R["order"] else "fail"), det

def _is_red(c):
    """Red-family fill: last 6 hex digits RRGGBB (any alpha), R >= 0xC0 and R exceeds G and B by >= 0x30.
    Accepts pure red (FF0000) and Excel's preset 'Light Red Fill' (FFC7CE); rejects green, yellow, white, grey."""
    c = str(c or "").upper()
    if len(c) not in (6, 8) or not re.fullmatch(r"[0-9A-F]+", c): return False
    r, g, b = (int(c[-6:][i:i + 2], 16) for i in (0, 2, 4))
    return r >= 0xC0 and r - g >= 0x30 and r - b >= 0x30

def e6_check(log, wd):
    wb, _, det = _load(wd, "e6.xlsx") if (wd / "e6.xlsx").exists() else (None, None, {"file": "e6.xlsx missing"})
    if wb is None: return "fail", det
    ws = _sheet(wb, "Sales"); h = _hdr(ws); L = openpyxl.utils.get_column_letter
    rc, tc = L(h.get("revenue", 8)), L(h.get("target", 9)); last = ws.max_row; rules = []
    for rng in ws.conditional_formatting:
        for rule in rng.rules:
            fill = rule.dxf.fill if rule.dxf else None; font = rule.dxf.font if rule.dxf else None
            cols = [str(getattr(x, "rgb", "") or "") for x in ((fill.fgColor, fill.bgColor, getattr(fill, "start_color", None)) if fill else ()) if x is not None]
            cols += [str(font.color.rgb)] if font is not None and font.color is not None else []
            red = any(_is_red(c) for c in cols)
            cover = any(cr.min_col <= h.get("revenue", 8) <= cr.max_col and cr.min_row <= 2 and cr.max_row >= last for cr in rng.sqref.ranges)
            fstr = " ".join(rule.formula or []).upper()
            logic = (rule.type == "expression" and rc in fstr and tc in fstr and "<" in fstr) or \
                    (rule.type == "cellIs" and rule.operator == "lessThan" and tc in fstr)
            rules.append({"range": str(rng.sqref), "type": rule.type, "op": rule.operator, "formula": rule.formula, "colors": cols,
                          "red": red, "covers_revenue_rows": cover, "logic_ok": logic})
    det.update({"cf_rules": rules[:5], "revenue_col": rc, "target_col": tc})
    if any(r["red"] and r["covers_revenue_rows"] and r["logic_ok"] for r in rules): return "pass", det
    return ("partial" if rules else "fail"), det

def e7_check(log, wd):
    p = wd / "e7.xlsx"
    if not p.exists(): return "fail", {"file": "e7.xlsx missing"}
    z = zipfile.ZipFile(p); charts = [n for n in z.namelist() if re.match(r"xl/charts/chart\d+\.xml", n)]
    xml = " ".join(z.read(n).decode("utf8", "replace") for n in charts)
    kind = "bar" if re.search(r"<(?:\w+:)?bar(?:3D)?Chart[ >]", xml) else "line" if re.search(r"<(?:\w+:)?line(?:3D)?Chart[ >]", xml) else None
    refs = re.findall(r"<(?:\w+:)?f>([^<]+)</(?:\w+:)?f>", xml); plots_b = any("monthly" in r.lower() and "$B$2" in r.replace("'", "") for r in refs)
    titled = "Monthly Revenue".lower() in re.sub(r"<[^>]+>", " ", xml).lower().replace("  ", " ")
    wv = recalc(p); ws = _sheet(wv, "Monthly") if wv else None
    vals_ok = bool(ws) and all(any(str(ws.cell(r, 1).value)[:7] == m and _close(ws.cell(r, 2).value, v) for r in range(2, 8)) for m, v in EREF["monthly"].items())
    det = {"chart_parts": charts, "chart_type": kind, "series_refs": refs[:4], "plots_TotalRevenue": plots_b, "title_found": titled, "monthly_values_ok": vals_ok}
    if kind and plots_b and titled and vals_ok: return "pass", det
    return ("partial" if kind else "fail"), det

def e8_check(log, wd):
    wb, wv, det = _load(wd, "e8.xlsx")
    if wb is None: return "fail", det
    ws, vs = _sheet(wb, "Clean"), (_sheet(wv, "Clean") if wv else None)
    if ws is None: return "fail", {**det, "error": "sheet Clean missing"}
    vs = vs or ws; h = _hdr(vs); need = ["custid", "name", "signup", "city", "state"]
    if not all(k in h for k in need): return "fail", {**det, "error": "columns missing", "headers": list(h)}
    ok = {k: 0 for k in need[1:]}; date_cells = 0; ref = EREF["customers"]
    for i, R in enumerate(ref):
        r = i + 2
        if str(vs.cell(r, h["custid"]).value) != R["CustID"]: continue
        for k, key in (("name", "Name"), ("city", "City"), ("state", "State")): ok[k] += str(vs.cell(r, h[k]).value).strip() == R[key] and "  " not in str(vs.cell(r, h[k]).value)
        v = vs.cell(r, h["signup"]).value
        if isinstance(v, (datetime, date)): date_cells += 1; ok["signup"] += v.strftime("%Y-%m-%d") == R["Signup"]
    det.update({"rows": len(ref), "correct": ok, "real_date_cells": date_cells})
    if all(v == len(ref) for v in ok.values()): return "pass", det
    return ("partial" if sum(ok.values()) >= 0.6 * 4 * len(ref) else "fail"), det

def _setup(files):
    def setup(wd):
        for f in files: shutil.copy(XD / f, wd / f)
        return [PYTHON_TOOL, SUBMIT_TOOL] + FILE_TOOLS, {"python_exec": make_python_exec(wd), **make_file_funcs(wd)}
    return setup

E_TESTS = {
    "E1": dict(title="Excel: pivot summary sheet (region x month revenue)", user=E1_USER, check=e1_check, setup=_setup(["sales.xlsx"]), wall=240),
    "E2": dict(title="Excel: nested-IF grade column as formulas", user=E2_USER, check=e2_check, setup=_setup(["sales.xlsx"]), wall=240),
    "E3": dict(title="Excel: VLOOKUP/XLOOKUP from second sheet as formulas", user=E3_USER, check=e3_check, setup=_setup(["sales.xlsx"]), wall=240),
    "E4": dict(title="Excel: SUMIFS/COUNTIFS/AVERAGEIFS summary formulas", user=E4_USER, check=e4_check, setup=_setup(["sales.xlsx"]), wall=240),
    "E5": dict(title="Excel: remove duplicates + filter + sort", user=E5_USER, check=e5_check, setup=_setup(["sales_dups.xlsx"]), wall=240),
    "E6": dict(title="Excel: conditional formatting (red below target)", user=E6_USER, check=e6_check, setup=_setup(["sales.xlsx"]), wall=240),
    "E7": dict(title="Excel: embedded bar/line chart", user=E7_USER, check=e7_check, setup=_setup(["sales.xlsx"]), wall=240),
    "E8": dict(title="Excel: text/date cleanup (TRIM, PROPER, dates, split)", user=E8_USER, check=e8_check, setup=_setup(["customers.xlsx"]), wall=240),
}
