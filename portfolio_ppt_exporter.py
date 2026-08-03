"""
PowerPoint exporter for the Portfolio Schedule Overview.
Dark-theme 16:9 slide matching the web UI exactly:
  - Navy background
  - Year / Calendar-Q / Fiscal-Q header rows
  - Per-project rows with colour-coded gate chips
  - TODAY dashed line with pill label
  - Legend footer
"""

from datetime import datetime
import os
import re

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt, Emu

# ── Palette (matches the web UI dark theme) ───────────────────────────────────
BG          = '0E1B35'   # slide background
NAVY_MID    = '1B2D52'   # year-strip / row odd
NAVY_DARK   = '122040'   # row even
NAVY_HEADER = '0A1628'   # calendar/fiscal row bg
GRID_LINE   = '2A3F6E'   # vertical quarter dividers
COL_DIV     = '2D4580'   # project-name column right border
WHITE       = 'FFFFFF'
MUTED       = '8899BB'   # secondary text
LABEL_TEXT  = 'C5D5EE'   # "Calendar" / "Fiscal" labels

# Gate chip colours
CHIP_DONE    = '43A047'   # signed-off  (green)
CHIP_PLANNED = 'F59E0B'   # planned     (amber/orange)
CHIP_PWR     = 'E05555'   # passed w/ rework (salmon/red)
CHIP_REWORK  = '66BB6A'   # rework sign-off (light green)

TODAY_COLOR  = 'E05555'   # today pill + line

CHIP_COLORS = {
    'done':    CHIP_DONE,
    'planned': CHIP_PLANNED,
    'pwr':     CHIP_PWR,
    'rework':  CHIP_REWORK,
}

LEGEND = [
    ('done',    'Done gate'),
    ('planned', 'Planned gate'),
    ('pwr',     'Passed w/ Rework'),
    ('rework',  'Rework sign-off'),
]


def _rgb(h):
    return RGBColor.from_string(h)


def _parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _fiscal_period(dt):
    return ((dt.month - 1 + 3) % 12) + 1


def _fiscal_year(dt):
    return dt.year + 1 if dt.month >= 10 else dt.year


def _fiscal_quarter(dt):
    shifted = (dt.month - 10) % 12
    return shifted // 3 + 1


def _cal_quarter(dt):
    return (dt.month - 1) // 3 + 1


def _pct(dt, rng_start, rng_end):
    total = (rng_end - rng_start).total_seconds()
    if total <= 0:
        return 0.5
    return max(0.0, min(1.0, (dt - rng_start).total_seconds() / total))


def _marker_status(item):
    if item.get('date_source') == 'Rework Due':
        return 'rework'
    if item.get('date_source') == 'Signed Off':
        if (item.get('sign_off_status') or '') == 'Passed with Rework':
            return 'pwr'
        return 'done'
    return 'planned'


def _chip_label(item):
    gname = item.get('gate_name') or 'Gate'
    status = _marker_status(item)
    if status == 'pwr':
        return gname + ' PWR'
    if status == 'rework':
        return gname + ' RW'
    return gname


def _sanitize(value):
    return re.sub(r'[<>:"/\\|?*]+', '_', str(value or '')).strip(' .') or 'portfolio'


# ── Low-level shape helpers ───────────────────────────────────────────────────

def _rect(slide, left, top, width, height, fill, line=None, radius=False):
    st = MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE if radius else MSO_AUTO_SHAPE_TYPE.RECTANGLE
    s = slide.shapes.add_shape(st, Inches(left), Inches(top), Inches(width), Inches(height))
    s.fill.solid()
    s.fill.fore_color.rgb = _rgb(fill)
    if line:
        s.line.color.rgb = _rgb(line)
        s.line.width = Pt(0.5)
    else:
        s.line.fill.background()
    return s


def _text(slide, left, top, width, height, txt,
          size=9, bold=False, italic=False, color=WHITE,
          align=PP_ALIGN.LEFT, wrap=True):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.text = txt
    p.alignment = align
    p.font.name = 'Segoe UI'
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.italic = italic
    p.font.color.rgb = _rgb(color)
    return tb


def _chip_textbox(slide, left, top, width, height,
                  line1, line2, line3,
                  size1=8.5, size2=6.5, size3=6.5):
    """Three-line chip text box (gate name / fiscal / date) all white, centred."""
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = False

    def _para(tf, txt, sz, bold=False, first=False):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        p.text = txt
        p.alignment = PP_ALIGN.CENTER
        p.font.name = 'Segoe UI'
        p.font.size = Pt(sz)
        p.font.bold = bold
        p.font.color.rgb = _rgb(WHITE)
        return p

    _para(tf, line1, size1, bold=True, first=True)
    _para(tf, line2, size2)
    _para(tf, line3, size3)


# ── Main exporter class ───────────────────────────────────────────────────────

class PortfolioScheduleExporter:

    # Layout (inches)
    W  = 13.333
    H  = 7.5
    LM = 0.18          # left margin
    LABEL_W = 1.72     # project-name column width
    TL  = 1.90         # timeline left x
    TW  = 11.25        # timeline width  (W - TL - 0.18 right margin)

    HDR_H  = 0.74      # title+subtitle block
    YR_H   = 0.27      # year strip
    CQ_H   = 0.21      # calendar quarter row
    FQ_H   = 0.21      # fiscal quarter row
    GRID_TOP = 0.74    # year strip top  (= HDR_H)
    PROJ_TOP = 1.43    # project rows top (= HDR_H + YR_H + CQ_H + FQ_H)
    FTR_H  = 0.38      # footer legend

    def export(self, timeline_data, division_name, output_folder):
        items = []
        for row in (timeline_data or []):
            dt = _parse_date(row.get('display_date'))
            if dt:
                items.append({**row, '_dt': dt})
        if not items:
            return None

        projects   = list(dict.fromkeys(i['project_name'] for i in items))
        all_dates  = [i['_dt'] for i in items]
        rng_start  = datetime(min(all_dates).year, 1, 1)
        rng_end    = datetime(max(all_dates).year, 12, 31)

        # Build months list
        months = []
        y, m = rng_start.year, 1
        while datetime(y, m, 1) <= rng_end:
            months.append(datetime(y, m, 1))
            m += 1
            if m > 12:
                m, y = 1, y + 1

        n  = len(projects)
        avail = self.H - self.PROJ_TOP - self.FTR_H
        rh = max(0.26, min(0.55, avail / max(1, n)))   # row height
        proj_font = max(6.0, min(9.5, rh * 15))

        prs = Presentation()
        prs.slide_width  = Inches(self.W)
        prs.slide_height = Inches(self.H)
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # ── Full background ──────────────────────────────────────────────────
        _rect(slide, 0, 0, self.W, self.H, BG)

        # ── Header ──────────────────────────────────────────────────────────
        _text(slide, self.LM + 0.05, 0.10, 9.0, 0.42,
              'Portfolio Schedule Overview',
              size=22, bold=True, color=WHITE)
        _text(slide, self.LM + 0.08, 0.52, 7.0, 0.20,
              'PLANNED MILESTONES & GATES',
              size=8, bold=False, color=MUTED)

        # Division + date (top right)
        _text(slide, self.W - 3.6, 0.12, 3.45, 0.20,
              division_name,
              size=8.5, bold=True, color=LABEL_TEXT, align=PP_ALIGN.RIGHT)
        _text(slide, self.W - 3.6, 0.35, 3.45, 0.20,
              f"Generated {datetime.now().strftime('%d %b %Y')}",
              size=8, color=MUTED, align=PP_ALIGN.RIGHT)

        # ── Draw timeline grid + header rows ─────────────────────────────────
        n_months = len(months)
        mw = self.TW / n_months if n_months else self.TW   # width per month

        self._draw_year_strip(slide, months, mw, rng_start, rng_end)
        self._draw_quarter_rows(slide, months, mw)
        self._draw_vertical_grid(slide, months, mw, n, rh)

        # ── Project name column right border ─────────────────────────────────
        _rect(slide, self.LM + self.LABEL_W, self.GRID_TOP,
              0.012, self.H - self.GRID_TOP - self.FTR_H, COL_DIV)

        # "Calendar" / "Fiscal" labels
        _text(slide, self.LM + 0.05,
              self.GRID_TOP + self.YR_H + 0.02,
              self.LABEL_W - 0.1, self.CQ_H - 0.04,
              'Calendar', size=7.5, color=LABEL_TEXT)
        _text(slide, self.LM + 0.05,
              self.GRID_TOP + self.YR_H + self.CQ_H + 0.02,
              self.LABEL_W - 0.1, self.FQ_H - 0.04,
              'Fiscal', size=7.5, color=LABEL_TEXT)

        # ── TODAY line + pill ────────────────────────────────────────────────
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_pct = _pct(today, rng_start, rng_end)
        if 0.0 <= today_pct <= 1.0:
            tx = self.TL + self.TW * today_pct

            # Pill
            pw, ph = 0.72, 0.22
            _rect(slide, tx - pw / 2, self.GRID_TOP + 0.02, pw, ph,
                  TODAY_COLOR, radius=True)
            _text(slide, tx - pw / 2, self.GRID_TOP + 0.02, pw, ph * 0.52,
                  'TODAY', size=6.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
            _text(slide, tx - pw / 2, self.GRID_TOP + 0.02 + ph * 0.48, pw, ph * 0.48,
                  f"{today.strftime('%b')} {today.day}",
                  size=6, color=WHITE, align=PP_ALIGN.CENTER)

            # Dashed line through project rows
            line_top  = self.PROJ_TOP
            line_h    = n * rh
            today_ln = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.LINE_INVERSE,
                Inches(tx), Inches(line_top),
                Inches(0.001), Inches(line_h),
            )
            today_ln.line.color.rgb = _rgb(TODAY_COLOR)
            today_ln.line.width = Pt(1.2)
            today_ln.line.dash_style = 4

        # ── Project rows + gate chips ────────────────────────────────────────
        chip_font1 = max(6.0, min(8.5, rh * 14))
        chip_font2 = max(5.0, min(7.0, rh * 11))
        chip_w     = max(0.60, min(0.82, rh * 1.4))
        chip_pad   = 0.04

        for idx, proj in enumerate(projects):
            row_top = self.PROJ_TOP + idx * rh
            row_bg  = NAVY_MID if idx % 2 == 0 else NAVY_DARK

            # Row background
            _rect(slide, 0, row_top, self.W, rh, row_bg)

            # Subtle bottom separator
            _rect(slide, 0, row_top + rh - 0.006, self.W, 0.006, GRID_LINE)

            # Project name (wrapping, vertically centred)
            name_top = row_top + max(0, (rh - proj_font / 72 * 1.6) / 2)
            _text(slide, self.LM + 0.06, name_top,
                  self.LABEL_W - 0.08, rh,
                  proj, size=proj_font, color=WHITE, wrap=True)

            # Gate chips for this project
            proj_items = sorted(
                [i for i in items if i['project_name'] == proj],
                key=lambda i: i['_dt']
            )
            chip_h  = rh - chip_pad * 2
            chip_top = row_top + chip_pad

            for item in proj_items:
                p = _pct(item['_dt'], rng_start, rng_end)
                cx  = self.TL + self.TW * p
                status = _marker_status(item)
                color  = CHIP_COLORS[status]

                # Chip background
                _rect(slide,
                      cx - chip_w / 2, chip_top,
                      chip_w, chip_h,
                      color, radius=True)

                # Three text lines inside chip
                label = _chip_label(item)
                fiscal = f"P{_fiscal_period(item['_dt'])} FY{_fiscal_year(item['_dt'])}"
                date_str = f"{item['_dt'].strftime('%b')} {item['_dt'].day}, {item['_dt'].year}"

                _chip_textbox(
                    slide,
                    cx - chip_w / 2 + 0.02, chip_top,
                    chip_w - 0.04, chip_h,
                    label, fiscal, date_str,
                    size1=chip_font1, size2=chip_font2, size3=chip_font2,
                )

        # ── Footer legend ────────────────────────────────────────────────────
        ftr_top = self.H - self.FTR_H
        _rect(slide, 0, ftr_top, self.W, self.FTR_H, NAVY_HEADER)
        _rect(slide, 0, ftr_top, self.W, 0.008, COL_DIV)

        lx = self.LM + 0.2
        ly = ftr_top + (self.FTR_H - 0.16) / 2
        for status_key, label in LEGEND:
            _rect(slide, lx, ly, 0.16, 0.16, CHIP_COLORS[status_key], radius=True)
            _text(slide, lx + 0.22, ly - 0.01, 1.2, 0.20,
                  label, size=7.5, color=WHITE)
            lx += 1.60

        # TODAY in legend
        _rect(slide, lx, ly + 0.05, 0.20, 0.008, TODAY_COLOR)
        _text(slide, lx + 0.26, ly - 0.01, 0.7, 0.20, 'Today', size=7.5, color=WHITE)

        # Dashed line indicator in legend
        try:
            dl = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.LINE_INVERSE,
                Inches(lx + 0.20), Inches(ly + 0.05),
                Inches(0.001), Inches(0.008))
            dl.line.color.rgb = _rgb(TODAY_COLOR)
            dl.line.width = Pt(1)
            dl.line.dash_style = 4
        except Exception:
            pass

        # ── Save ─────────────────────────────────────────────────────────────
        ts = datetime.now().strftime('%d-%m-%y_%H%M')
        fname = f"Portfolio_Schedule_Overview_{_sanitize(division_name)}_{ts}.pptx"
        os.makedirs(output_folder, exist_ok=True)
        path = os.path.join(output_folder, fname)
        prs.save(path)
        return path

    # ── Header rows ──────────────────────────────────────────────────────────

    def _draw_year_strip(self, slide, months, mw, rng_start, rng_end):
        top = self.GRID_TOP
        h   = self.YR_H
        # Background already dark from full BG; draw a slightly lighter strip
        _rect(slide, self.TL, top, self.TW, h, NAVY_MID)
        years = sorted({m.year for m in months})
        for yr in years:
            yr_m = [m for m in months if m.year == yr]
            i0   = months.index(yr_m[0])
            x    = self.TL + i0 * mw
            w    = len(yr_m) * mw
            _text(slide, x + 0.05, top + 0.03, w - 0.1, h - 0.06,
                  str(yr), size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
            # Right border
            _rect(slide, x + w - 0.008, top, 0.008, h, GRID_LINE)

    def _draw_quarter_rows(self, slide, months, mw):
        n_months = len(months)
        cq_top = self.GRID_TOP + self.YR_H
        fq_top = cq_top + self.CQ_H

        # Calendar quarters
        _rect(slide, self.TL, cq_top, self.TW, self.CQ_H, NAVY_DARK)
        for i in range(0, n_months, 3):
            m   = months[i]
            x   = self.TL + i * mw
            w   = min(3, n_months - i) * mw
            cq  = _cal_quarter(m)
            # Alternating shade
            bg = NAVY_MID if (i // 3) % 2 == 0 else NAVY_DARK
            _rect(slide, x, cq_top, w, self.CQ_H, bg)
            _text(slide, x + 0.02, cq_top + 0.02, w - 0.04, self.CQ_H - 0.04,
                  f'Q{cq}', size=8, bold=True, color=LABEL_TEXT, align=PP_ALIGN.CENTER)
            _rect(slide, x + w - 0.006, cq_top, 0.006, self.CQ_H, GRID_LINE)

        # Fiscal quarters
        _rect(slide, self.TL, fq_top, self.TW, self.FQ_H, NAVY_HEADER)
        for i in range(0, n_months, 3):
            m   = months[i]
            x   = self.TL + i * mw
            w   = min(3, n_months - i) * mw
            fq  = _fiscal_quarter(m)
            fy  = _fiscal_year(m)
            _text(slide, x + 0.01, fq_top + 0.02, w - 0.02, self.FQ_H - 0.04,
                  f'FQ{fq} FY{fy}', size=7, color=MUTED, align=PP_ALIGN.CENTER)
            _rect(slide, x + w - 0.006, fq_top, 0.006, self.FQ_H, GRID_LINE)

    def _draw_vertical_grid(self, slide, months, mw, n_projects, rh):
        """Light vertical lines at every quarter boundary through the project area."""
        proj_h = n_projects * rh
        n_months = len(months)
        for i in range(0, n_months, 3):
            x = self.TL + i * mw
            _rect(slide, x, self.PROJ_TOP, 0.006, proj_h, GRID_LINE)
