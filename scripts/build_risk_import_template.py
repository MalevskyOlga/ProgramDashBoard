"""
Generates the standardized Risk Register import template (Risk_Import_Template.xlsx).

This mirrors exactly what server.py's `_parse_risks_from_excel()` reads:
  - A sheet whose name contains "risk input" (case-insensitive)
  - Header row at row 4, data starting row 5
  - 1-based columns: 2=Risk ID (blank here since these are brand-new risks; when
    re-importing an exported file, a filled-in Risk ID updates that existing risk
    instead of creating a duplicate), 4=Category, 5=Risk Statement, 6=Prob,
    7=Impact, 9=Schedule Impact (Weeks), 10=Risk Type, 12=Strategy, 13=Action Plan,
    14=Owner, 15=Status, 16=Outcome, 17=Date Closed
  - Columns 1,3,8,11 are NOT read by the importer (kept for user reference only)

Run once to (re)generate the template:
    python scripts/build_risk_import_template.py
"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

OUT_PATH = "risk_import_template/Risk_Import_Template.xlsx"

# Column layout (1-based). "imported" = read by _parse_risks_from_excel.
COLUMNS = [
    (1,  "#",                         10, False, None),
    (2,  "Risk ID — don't edit",  10, True,  None),
    (3,  "Date Added",                12, False, None),
    (4,  "Risk Category",             16, True,  ["Technical", "Schedule", "Cost / Quality", "Supply Chain",
                                                    "Regulatory", "Marketing", "Design", "Other"]),
    (5,  "Risk Statement",            45, True,  None),
    (6,  "Prob",                      11, True,  ["Low", "Medium", "High", "Very High"]),
    (7,  "Impact",                    11, True,  ["Low", "Medium", "High", "Very High"]),
    (8,  "Risk RPN (not imported)",   12, False, None),
    (9,  "Schedule Impact (Weeks)",   14, True,  None),
    (10, "Risk Type",                 10, True,  ["Type 1", "Type 2", "Type 3"]),
    (11, "Risk Exposure (not imported)", 14, False, None),
    (12, "Risk Management Strategy",  16, True,  ["Mitigate", "Accept", "Transfer", "Avoid", "Watch"]),
    (13, "Action Plan",               40, True,  None),
    (14, "Owner",                     16, True,  None),
    (15, "Status",                    12, True,  ["In Process", "Assigned", "Canceled", "Completed"]),
    (16, "Outcome",                   24, True,  None),
    (17, "Date Closed",               12, True,  None),
]

REQUIRED_COL = 5  # Risk Statement — rows with this blank are skipped entirely on import
HEADER_ROW = 4
FIRST_DATA_ROW = 5
LAST_VALIDATED_ROW = 200

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Risk Input"

navy = "1E3A5F"
imported_fill = PatternFill("solid", fgColor=navy)
not_imported_fill = PatternFill("solid", fgColor="9CA3AF")
example_fill = PatternFill("solid", fgColor="FFF3CD")
header_font = Font(bold=True, color="FFFFFF", size=10)
title_font = Font(bold=True, size=14, color=navy)
subtitle_font = Font(italic=True, size=10, color="64748B")
thin = Side(style="thin", color="D8DEE6")
border = Border(left=thin, right=thin, top=thin, bottom=thin)

# Title block (rows 1-3) — cosmetic only, not read by the importer
ws.merge_cells("A1:Q1")
ws["A1"] = "RISK REGISTER — Import Template"
ws["A1"].font = title_font

ws.merge_cells("A2:Q2")
ws["A2"] = ("Columns shaded NAVY are imported by the system. Columns shaded GREY are for your own "
            "reference only and are ignored on import. Row 5 below is an example — delete it before "
            "uploading your real risks. Risk Statement (column E) is the only required field; a row "
            "with no Risk Statement is skipped silently. Leave Risk ID (column B) blank for new risks — "
            "it's only used when re-importing a file exported from the dashboard, to update an existing "
            "risk instead of creating a duplicate.")
ws["A2"].font = subtitle_font
ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
ws.row_dimensions[2].height = 60

ws.merge_cells("A3:Q3")
ws["A3"] = "Sheet name must contain “Risk Input” (this sheet is already named correctly — do not rename it)."
ws["A3"].font = subtitle_font

# Header row
for col, label, width, imported, _choices in COLUMNS:
    cell = ws.cell(row=HEADER_ROW, column=col, value=label)
    cell.font = header_font
    cell.fill = imported_fill if imported else not_imported_fill
    cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    cell.border = border
    ws.column_dimensions[get_column_letter(col)].width = width
ws.row_dimensions[HEADER_ROW].height = 30
ws.freeze_panes = "F5"

# Data validation dropdowns (applied to the full usable range, not just the example row)
for col, _label, _width, _imported, choices in COLUMNS:
    if not choices:
        continue
    letter = get_column_letter(col)
    formula = '"{}"'.format(",".join(choices))
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False)
    dv.add(f"{letter}{FIRST_DATA_ROW}:{letter}{LAST_VALIDATED_ROW}")
    ws.add_data_validation(dv)

# One example row, clearly marked, matching the field names/values the system actually recognizes
example = {
    1: 1, 2: "", 3: "2026-10-25",
    4: "Technical", 5: "EXAMPLE — delete this row: Supplier qualification may slip past Gate 3",
    6: "Medium", 7: "High", 8: "", 9: 4,
    10: "Type 1", 11: "",
    12: "Mitigate", 13: "Run parallel qualification with backup supplier",
    14: "Jane Doe", 15: "In Process", 16: "", 17: "",
}
for col, value in example.items():
    cell = ws.cell(row=FIRST_DATA_ROW, column=col, value=value if value != "" else None)
    cell.fill = example_fill
    cell.border = border
    cell.alignment = Alignment(wrap_text=True, vertical="top")
ws.row_dimensions[FIRST_DATA_ROW].height = 32

# Light borders on the next ~40 blank rows so the sheet looks like a ready-to-fill table
for r in range(FIRST_DATA_ROW + 1, FIRST_DATA_ROW + 40):
    for col, *_ in COLUMNS:
        ws.cell(row=r, column=col).border = border

import os
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
wb.save(OUT_PATH)
print(f"Wrote {OUT_PATH}")
