"""Correct and deliberately wrong solutions for E1-E8, used to validate the checkers offline."""
import shutil, sys, json
from pathlib import Path
import pandas as pd, openpyxl
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import PatternFill
from openpyxl.chart import BarChart, Reference
from openpyxl.utils import get_column_letter as L

def solve(tid, wd, wrong=False):
    wd = Path(wd); S = pd.read_excel(wd / "sales.xlsx", sheet_name="Sales") if (wd / "sales.xlsx").exists() else None
    if tid == "E1":
        p = S.pivot_table(index="Region", columns="Month", values="Revenue", aggfunc="sum" if not wrong else "mean").sort_index()
        p.index.name = "Region"; p.columns.name = None
        with pd.ExcelWriter(wd / "e1.xlsx") as xw: p.to_excel(xw, sheet_name="Pivot")
    elif tid in ("E2", "E3", "E6"):
        wb = openpyxl.load_workbook(wd / "sales.xlsx"); ws = wb["Sales"]; n = ws.max_row
        if tid == "E2":
            ws.cell(1, 10, "Grade")
            for r in range(2, n + 1):
                ws.cell(r, 10, f'=IF(H{r}>=1.1*I{r},"A",IF(H{r}>=I{r},"B",IF(H{r}>=0.8*I{r},"C","D")))' if not wrong else "B")
        if tid == "E3":
            ws.cell(1, 10, "Category"); ws.cell(1, 11, "Price_per_t")
            for r in range(2, n + 1):
                ws.cell(r, 10, f"=VLOOKUP(F{r},Products!$A$2:$C$6,2,FALSE)")
                ws.cell(r, 11, f"=_xlfn.XLOOKUP(F{r},Products!$A$2:$A$6,Products!$C$2:$C$6)" if not wrong else f"=VLOOKUP(F{r},Products!$A$2:$C$6,2,TRUE)")
        if tid == "E6":
            red = PatternFill(start_color="FFFF0000", end_color="FFFF0000", fill_type="solid")
            if wrong:
                for r in range(2, n + 1):
                    if ws.cell(r, 8).value < ws.cell(r, 9).value: ws.cell(r, 8).fill = red
            else: ws.conditional_formatting.add(f"H2:H{n}", FormulaRule(formula=["$H2<$I2"], fill=red))
        wb.save(wd / f"{tid.lower()}.xlsx")
    elif tid == "E4":
        wb = openpyxl.load_workbook(wd / "sales.xlsx"); ws = wb.create_sheet("Summary"); n = wb["Sales"].max_row
        ws.append(["Region", "Total_Revenue", "Orders", "Avg_Qty"])
        for i, rg in enumerate(sorted(S.Region.unique()), start=2):
            ws.append([rg, f"=SUMIFS(Sales!$H$2:$H${n},Sales!$D$2:$D${n},A{i})",
                       f"=COUNTIFS(Sales!$D$2:$D${n},A{i})", f"=AVERAGEIFS(Sales!$G$2:$G${n},Sales!$D$2:$D${n},A{i})" if not wrong else 5])
        ws["F1"] = "North_PPC_Revenue"; ws["F2"] = f'=SUMIFS(Sales!$H$2:$H${n},Sales!$D$2:$D${n},"North",Sales!$F$2:$F${n},"Blend-P")'
        wb.save(wd / "e4.xlsx")
    elif tid == "E5":
        D = pd.read_excel(wd / "sales_dups.xlsx", sheet_name="Sales"); nd = D if wrong else D.drop_duplicates()
        out = nd[(nd.Qty_t >= 20) & nd.Region.isin(["North", "West"])].sort_values(["Revenue", "OrderID"], ascending=[False, True])
        with pd.ExcelWriter(wd / "e5.xlsx") as xw: out.to_excel(xw, sheet_name="Clean", index=False)
        res = {"rows_before": len(D), "duplicates_removed": len(D) - len(nd), "rows_after": len(out)}; print(json.dumps(res)); return res
    elif tid == "E7":
        m = S.groupby("Month").Revenue.sum().reset_index(); wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Monthly"
        ws.append(["Month", "Total_Revenue"]); [ws.append([a, int(b)]) for a, b in m.values]
        if not wrong:
            ch = BarChart(); ch.title = "Monthly Revenue"; ch.add_data(Reference(ws, min_col=2, min_row=1, max_row=7), titles_from_data=True)
            ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=7)); ws.add_chart(ch, "D2")
        wb.save(wd / "e7.xlsx")
    elif tid == "E8":
        C = pd.read_excel(wd / "customers.xlsx", sheet_name="Customers")
        name = C.CustName.str.split().str.join(" ").str.title()
        d = pd.to_datetime(C.SignupDate, format="mixed", dayfirst=True) if wrong else pd.Series([pd.to_datetime(x, format=f) for x in C.SignupDate for f in [("%Y-%m-%d" if "-" in x else "%d/%m/%Y" if "/" in x else "%d %b %Y")]])
        loc = C.Location.str.split("-", n=1)
        out = pd.DataFrame({"CustID": C.CustID, "Name": name if not wrong else C.CustName, "Signup": d,
                            "City": loc.str[0].str.strip().str.title(), "State": loc.str[1].str.strip().str.title()})
        with pd.ExcelWriter(wd / "e8.xlsx") as xw: out.to_excel(xw, sheet_name="Clean", index=False)
