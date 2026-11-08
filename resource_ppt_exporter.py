"""PowerPoint builder for the Overall Resource Load tab.

The browser sends the data behind the sections the user ticked (load chart, monthly
load heatmap, by discipline, by project) plus the task rows ticked on a person's page.
This module turns that into a deck: a title slide, the ticked sections in a fixed
order, then one or more slides per owner whose tasks were ticked.
"""
import io
from datetime import date

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREY = RGBColor(0x5B, 0x64, 0x70)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x22, 0x22, 0x22)
ZEBRA = RGBColor(0xF7, 0xF8, 0xFA)
EMPTY_BG = RGBColor(0xF1, 0xF2, 0xF4)
OK_BG, OK_FG = RGBColor(0xDC, 0xF2, 0xE3), RGBColor(0x1B, 0x5E, 0x20)
WARN_BG, WARN_FG = RGBColor(0xFE, 0xF3, 0xC7), RGBColor(0x92, 0x40, 0x0E)
HEAVY_BG, HEAVY_FG = RGBColor(0xFD, 0xE3, 0xCF), RGBColor(0x9A, 0x3C, 0x00)
BAD_BG, BAD_FG = RGBColor(0xFD, 0xEC, 0xEA), RGBColor(0xB9, 0x1C, 0x1C)
BAR_OK = RGBColor(0x2E, 0x7D, 0x5B)
BAR_OVER = RGBColor(0xC6, 0x28, 0x28)

TONES = {'ok': (OK_BG, OK_FG), 'warn': (WARN_BG, WARN_FG), 'bad': (BAD_BG, BAD_FG), 'none': (EMPTY_BG, GREY)}

ROWS_PER_SLIDE = 14
MONTHS_PER_SLIDE = 12
DISCIPLINES_PER_SLIDE = 10
OWNERS_PER_CHART = 15
SLIDE_W, SLIDE_H = 13.333, 7.5


def _chunks(items, size):
    """Split a list into pages; an empty list gives no pages."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def _set_cell(cell, text, size=10, bold=False, color=DARK, fill=None, align=PP_ALIGN.CENTER):
    cell.text = '' if text is None else str(text)
    cell.margin_left = cell.margin_right = Inches(0.05)
    cell.margin_top = cell.margin_bottom = Inches(0.02)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    for paragraph in cell.text_frame.paragraphs:
        paragraph.alignment = align
        for run in paragraph.runs:
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill


class ResourceLoadPptExporter:
    def __init__(self, division_name):
        self.division_name = division_name or 'Portfolio'
        self.prs = Presentation()
        self.prs.slide_width = Inches(SLIDE_W)
        self.prs.slide_height = Inches(SLIDE_H)
        self.blank = self.prs.slide_layouts[6]

    # ── public ─────────────────────────────────────────────────────────────
    def build(self, data):
        sections = set(data.get('sections') or [])
        self._title_slide(sections, len(data.get('tasks') or []))
        if 'loadchart' in sections and data.get('loadChart'):
            self._load_chart(data['loadChart'])
        if 'heatmap' in sections and data.get('heatmap'):
            self._heatmap(data['heatmap'])
        if 'discipline' in sections and data.get('discipline'):
            self._discipline(data['discipline'])
        if 'projectmatrix' in sections and data.get('projectMatrix'):
            self._project_matrix(data['projectMatrix'])
        self._task_slides(data.get('tasks') or [])
        buf = io.BytesIO()
        self.prs.save(buf)
        buf.seek(0)
        return buf

    # ── helpers ────────────────────────────────────────────────────────────
    def _slide(self, title, subtitle=''):
        slide = self.prs.slides.add_slide(self.blank)
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.7))
        box.text_frame.word_wrap = True
        p = box.text_frame.paragraphs[0]
        p.text = title
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = NAVY
        if subtitle:
            sub = slide.shapes.add_textbox(Inches(0.5), Inches(0.95), Inches(12.3), Inches(0.4))
            sub.text_frame.word_wrap = True
            sp = sub.text_frame.paragraphs[0]
            sp.text = subtitle
            sp.font.size = Pt(13)
            sp.font.color.rgb = GREY
        foot = slide.shapes.add_textbox(Inches(0.5), Inches(7.05), Inches(12.3), Inches(0.3))
        fp = foot.text_frame.paragraphs[0]
        fp.text = f'{self.division_name} · Overall Resource Load'
        fp.font.size = Pt(9)
        fp.font.color.rgb = GREY
        return slide

    def _table(self, slide, headers, rows, widths, styles=None, font=10, left_cols=(0,)):
        styles = styles or {}
        n_rows = len(rows) + 1
        shape = slide.shapes.add_table(n_rows, len(headers), Inches(0.5), Inches(1.45),
                                       Inches(sum(widths)), Inches(0.34 * n_rows))
        table = shape.table
        for c, w in enumerate(widths):
            table.columns[c].width = Inches(w)
        for c, h in enumerate(headers):
            _set_cell(table.cell(0, c), h, size=font, bold=True, color=WHITE, fill=NAVY,
                      align=PP_ALIGN.LEFT if c in left_cols else PP_ALIGN.CENTER)
        for r, row in enumerate(rows, 1):
            zebra = WHITE if r % 2 else ZEBRA
            for c, value in enumerate(row):
                fill, fg = styles.get((r, c), (zebra, DARK))
                _set_cell(table.cell(r, c), value, size=font, color=fg, fill=fill,
                          align=PP_ALIGN.LEFT if c in left_cols else PP_ALIGN.CENTER)
        return shape

    # ── slides ─────────────────────────────────────────────────────────────
    def _title_slide(self, sections, task_count):
        slide = self.prs.slides.add_slide(self.blank)
        box = slide.shapes.add_textbox(Inches(0.8), Inches(2.3), Inches(11.7), Inches(2.5))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = 'Overall Resource Load'
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = NAVY
        p2 = tf.add_paragraph()
        p2.text = self.division_name
        p2.font.size = Pt(24)
        p2.font.color.rgb = GREY
        p3 = tf.add_paragraph()
        p3.text = date.today().strftime('%d %b %Y')
        p3.font.size = Pt(16)
        p3.font.color.rgb = GREY
        labels = {'loadchart': 'Load chart', 'heatmap': 'Monthly load heatmap',
                  'discipline': 'By discipline', 'projectmatrix': 'By project'}
        included = [labels[k] for k in labels if k in sections]
        if task_count:
            included.append(f'{task_count} selected task(s)')
        if included:
            p4 = tf.add_paragraph()
            p4.text = 'Contents: ' + ' · '.join(included)
            p4.font.size = Pt(14)
            p4.font.color.rgb = GREY

    def _load_chart(self, rows):
        items = sorted(rows, key=lambda r: -(r.get('load') or 0))
        pages = _chunks(items, OWNERS_PER_CHART)
        for page_no, chunk in enumerate(pages, 1):
            subtitle = 'Concurrent load per owner · red bars = at or above the overload threshold'
            if len(pages) > 1:
                subtitle += f' · page {page_no} of {len(pages)}'
            slide = self._slide('Load chart', subtitle)
            cd = CategoryChartData()
            cd.categories = [r.get('owner', '') for r in chunk]
            cd.add_series('Concurrent load', [r.get('load') or 0 for r in chunk])
            frame = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.45),
                                           Inches(12.3), Inches(5.5), cd)
            chart = frame.chart
            chart.has_legend = False
            plot = chart.plots[0]
            plot.gap_width = 60
            plot.has_data_labels = True
            plot.data_labels.font.size = Pt(11)
            plot.data_labels.number_format = '0'
            plot.data_labels.number_format_is_linked = False
            chart.category_axis.reverse_order = True
            chart.category_axis.tick_labels.font.size = Pt(11)
            chart.value_axis.tick_labels.font.size = Pt(10)
            chart.value_axis.has_major_gridlines = False
            series = plot.series[0]
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = BAR_OK
            for i, r in enumerate(chunk):
                if (r.get('load') or 0) >= (r.get('threshold') or 5):
                    point = series.points[i]
                    point.format.fill.solid()
                    point.format.fill.fore_color.rgb = BAR_OVER

    def _heatmap(self, hm):
        months = hm.get('months') or []
        rows = hm.get('rows') or []
        if not months or not rows:
            return
        peak = max([1] + [c for r in rows for c in (r.get('cells') or [])])
        row_pages = _chunks(rows, ROWS_PER_SLIDE)
        month_pages = _chunks(list(range(len(months))), MONTHS_PER_SLIDE)
        for mp, midx in enumerate(month_pages, 1):
            for rp, rchunk in enumerate(row_pages, 1):
                subtitle = 'Overlapping tasks per owner per month · colour = share of the busiest month'
                if len(month_pages) > 1 or len(row_pages) > 1:
                    subtitle += f' · page {mp}.{rp}'
                slide = self._slide('Monthly load heatmap', subtitle)
                headers = ['Owner'] + [months[i] for i in midx]
                body, styles = [], {}
                for r_i, r in enumerate(rchunk, 1):
                    cells = r.get('cells') or []
                    body.append([r.get('owner', '')] + [
                        '–' if not cells[i] else cells[i] for i in midx])
                    for c_i, i in enumerate(midx, 1):
                        n = cells[i] if i < len(cells) else 0
                        if not n:
                            styles[(r_i, c_i)] = (EMPTY_BG, GREY)
                        elif n / peak >= 0.75:
                            styles[(r_i, c_i)] = (BAD_BG, BAD_FG)
                        elif n / peak >= 0.40:
                            styles[(r_i, c_i)] = (WARN_BG, WARN_FG)
                        else:
                            styles[(r_i, c_i)] = (OK_BG, OK_FG)
                widths = [2.9] + [(12.3 - 2.9) / len(midx)] * len(midx)
                self._table(slide, headers, body, widths, styles, font=10)

    def _discipline(self, disc):
        months = disc.get('months') or []
        rows = disc.get('rows') or []
        if not months or not rows:
            return
        row_pages = _chunks(rows, ROWS_PER_SLIDE)
        month_pages = _chunks(list(range(len(months))), MONTHS_PER_SLIDE)
        for mp, midx in enumerate(month_pages, 1):
            for rp, rchunk in enumerate(row_pages, 1):
                subtitle = 'Tasks per discipline per month · colour = tasks per owner'
                if len(month_pages) > 1 or len(row_pages) > 1:
                    subtitle += f' · page {mp}.{rp}'
                slide = self._slide('By discipline', subtitle)
                headers = ['Discipline (owners)'] + [months[i] for i in midx]
                body, styles = [], {}
                for r_i, r in enumerate(rchunk, 1):
                    counts = r.get('counts') or []
                    owners = r.get('owner_count') or 1
                    body.append([f"{r.get('name', '')} ({owners})"] + [
                        '–' if not counts[i] else counts[i] for i in midx])
                    for c_i, i in enumerate(midx, 1):
                        n = counts[i] if i < len(counts) else 0
                        if not n:
                            styles[(r_i, c_i)] = (EMPTY_BG, GREY)
                            continue
                        ratio = n / max(owners, 1)
                        if ratio <= 1:
                            styles[(r_i, c_i)] = (OK_BG, OK_FG)
                        elif ratio <= 2:
                            styles[(r_i, c_i)] = (WARN_BG, WARN_FG)
                        elif ratio <= 3.5:
                            styles[(r_i, c_i)] = (HEAVY_BG, HEAVY_FG)
                        else:
                            styles[(r_i, c_i)] = (BAD_BG, BAD_FG)
                widths = [2.9] + [(12.3 - 2.9) / len(midx)] * len(midx)
                self._table(slide, headers, body, widths, styles, font=10)

    def _project_matrix(self, pm):
        discs = pm.get('disciplines') or []
        rows = pm.get('rows') or []
        if not discs or not rows:
            return
        row_pages = _chunks(rows, ROWS_PER_SLIDE)
        disc_pages = _chunks(list(range(len(discs))), DISCIPLINES_PER_SLIDE)
        for dp, didx in enumerate(disc_pages, 1):
            for rp, rchunk in enumerate(row_pages, 1):
                subtitle = 'Staffing coverage per project and discipline'
                if len(disc_pages) > 1 or len(row_pages) > 1:
                    subtitle += f' · page {dp}.{rp}'
                slide = self._slide('By project', subtitle)
                headers = ['Project', 'Leader'] + [discs[i] for i in didx]
                body, styles = [], {}
                for r_i, r in enumerate(rchunk, 1):
                    cells = r.get('cells') or []
                    body.append([r.get('name', ''), r.get('leader', '')] + [
                        (cells[i] or {}).get('label', '') if i < len(cells) else '' for i in didx])
                    for c_i, i in enumerate(didx, 2):
                        cell = cells[i] if i < len(cells) else {}
                        styles[(r_i, c_i)] = TONES.get((cell or {}).get('tone', 'none'), TONES['none'])
                rest = 12.3 - 3.2 - 1.8
                widths = [3.2, 1.8] + [rest / len(didx)] * len(didx)
                self._table(slide, headers, body, widths, styles, font=9, left_cols=(0, 1))

    def _task_slides(self, tasks):
        if not tasks:
            return
        groups, order = {}, []
        for t in tasks:
            owner = t.get('owner') or 'Unassigned'
            if owner not in groups:
                groups[owner] = []
                order.append(owner)
            groups[owner].append(t)
        headers = ['Project', 'Phase', 'Task', 'Start', 'End', 'Status', 'Work days']
        widths = [2.4, 1.6, 3.6, 1.1, 1.1, 1.6, 0.9]
        for owner in order:
            rows = sorted(groups[owner], key=lambda t: (t.get('start_date') or '', t.get('project_name') or ''))
            pages = _chunks(rows, ROWS_PER_SLIDE)
            for page_no, chunk in enumerate(pages, 1):
                subtitle = f'{len(rows)} selected task(s)'
                if len(pages) > 1:
                    subtitle += f' · page {page_no} of {len(pages)}'
                slide = self._slide(f'Tasks — {owner}', subtitle)
                body, styles = [], {}
                for r_i, t in enumerate(chunk, 1):
                    status = t.get('status') or ''
                    if t.get('is_delayed'):
                        status = f'{status} ⚠ delayed'
                        styles[(r_i, 5)] = (BAD_BG, BAD_FG)
                    body.append([
                        t.get('project_name') or '',
                        t.get('phase') or '—',
                        t.get('task_name') or '',
                        t.get('start_date') or '—',
                        t.get('end_date') or '—',
                        status,
                        f"{t.get('working_days') or 0}d",
                    ])
                self._table(slide, headers, body, widths, styles, font=10, left_cols=(0, 1, 2))
