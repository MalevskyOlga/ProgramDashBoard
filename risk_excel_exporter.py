"""
Risk Register Excel Exporter

Writes risks into the exact "Risk Input" layout that server.py's
_parse_risks_from_excel() reads back in, so an exported file:
  - can be edited and re-uploaded via Import Excel unchanged, and
  - doubles as a live, correctly-formatted example of the import template.

Column layout (1-based) must stay in sync with _parse_risks_from_excel():
  4=Category, 5=Risk Statement, 6=Prob, 7=Impact, 9=Schedule Impact (Weeks),
  10=Risk Type, 12=Strategy, 13=Action Plan, 14=Owner, 15=Status,
  16=Outcome, 17=Date Closed. Columns 1,2,3,8,11 are not read on import.
"""
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

NAVY = "1E3A5F"
HEADER_ROW = 4
FIRST_DATA_ROW = 5
LAST_VALIDATED_ROW = 500

# (column, header label, width, imported-by-parser, dropdown choices or None)
COLUMNS = [
    (1,  "#",                             10, False, None),
    (2,  "Risk ID",                       10, False, None),
    (3,  "Date Added",                    12, False, None),
    (4,  "Risk Category",                 16, True,  ["Technical", "Schedule", "Cost / Quality", "Supply Chain",
                                                        "Regulatory", "Marketing", "Design", "Other"]),
    (5,  "Risk Statement",                45, True,  None),
    (6,  "Prob",                          11, True,  ["Low", "Medium", "High", "Very High"]),
    (7,  "Impact",                        11, True,  ["Low", "Medium", "High", "Very High"]),
    (8,  "Risk RPN (not imported)",       12, False, None),
    (9,  "Schedule Impact (Weeks)",       14, True,  None),
    (10, "Risk Type",                     10, True,  ["Type 1", "Type 2", "Type 3"]),
    (11, "Risk Exposure (not imported)",  14, False, None),
    (12, "Risk Management Strategy",      16, True,  ["Mitigate", "Accept", "Transfer", "Avoid", "Watch"]),
    (13, "Action Plan",                   40, True,  None),
    (14, "Owner",                         16, True,  None),
    (15, "Status",                        12, True,  ["Open", "Assigned", "In Process", "Mitigated", "Closed"]),
    (16, "Outcome",                       24, True,  None),
    (17, "Date Closed",                   12, True,  None),
]

_PROB_SCORE = {'Low': 2, 'Medium': 3, 'High': 4, 'Very High': 5}


def _rpn(prob, impact):
    return _PROB_SCORE.get(prob, 3) * _PROB_SCORE.get(impact, 3)


def _date_only(value):
    return (value or '')[:10] or None


def export_risks_to_excel(title, risks):
    """Build an .xlsx in the standard Risk Input layout, populated with `risks`
    (a list of dicts shaped like database_manager.get_risks()/get_pipeline_risks()
    rows). `title` names the project/pipeline-project in the sheet's title block.
    Returns a BytesIO positioned at 0, ready for flask.send_file.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Risk Input"

    imported_fill = PatternFill("solid", fgColor=NAVY)
    not_imported_fill = PatternFill("solid", fgColor="9CA3AF")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    title_font = Font(bold=True, size=14, color=NAVY)
    subtitle_font = Font(italic=True, size=10, color="64748B")
    thin = Side(style="thin", color="D8DEE6")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:Q1")
    ws["A1"] = f"RISK REGISTER — {title}"
    ws["A1"].font = title_font

    ws.merge_cells("A2:Q2")
    ws["A2"] = ("Exported from the dashboard. NAVY columns are read back in on import; GREY columns "
                "are for reference only. Edit freely and re-upload via Import Excel.")
    ws["A2"].font = subtitle_font
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 32

    ws.merge_cells("A3:Q3")
    ws["A3"] = "Sheet name must contain “Risk Input” (already correct — do not rename)."
    ws["A3"].font = subtitle_font

    for col, label, width, imported, _choices in COLUMNS:
        cell = ws.cell(row=HEADER_ROW, column=col, value=label)
        cell.font = header_font
        cell.fill = imported_fill if imported else not_imported_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[HEADER_ROW].height = 30
    ws.freeze_panes = "F5"

    for col, _label, _width, _imported, choices in COLUMNS:
        if not choices:
            continue
        letter = get_column_letter(col)
        formula = '"{}"'.format(",".join(choices))
        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False)
        dv.add(f"{letter}{FIRST_DATA_ROW}:{letter}{LAST_VALIDATED_ROW}")
        ws.add_data_validation(dv)

    row_num = FIRST_DATA_ROW
    for i, r in enumerate(risks, start=1):
        prob = r.get('probability') or 'Medium'
        impact = r.get('impact') or 'Medium'
        values = {
            1: i,
            2: r.get('id'),
            3: _date_only(r.get('created_at')),
            4: r.get('category') or 'Other',
            5: r.get('title') or '',
            6: prob,
            7: impact,
            8: _rpn(prob, impact),
            9: r.get('schedule_impact_weeks'),
            10: r.get('risk_type') or 'Type 1',
            11: None,
            12: r.get('strategy') or 'Mitigate',
            13: r.get('mitigation') or '',
            14: r.get('owner') or '',
            15: r.get('status') or 'Open',
            16: r.get('outcome'),
            17: _date_only(r.get('date_closed')),
        }
        for col, value in values.items():
            cell = ws.cell(row=row_num, column=col, value=value)
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row_num].height = 34
        row_num += 1

    # A handful of extra bordered blank rows so the sheet looks ready for more entries
    for r in range(row_num, row_num + 15):
        for col, *_ in COLUMNS:
            ws.cell(row=r, column=col).border = border

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
