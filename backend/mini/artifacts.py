"""Validated, reproducible files stored as small source specifications.

The workspace stores text and structured content; Render renders the binary only
when an authenticated client downloads it. No filesystem or public file URLs.
"""
import io
import json
import re
from html import escape


MIME = {
    'md': 'text/markdown; charset=utf-8',
    'txt': 'text/plain; charset=utf-8',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf': 'application/pdf',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


def title(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError('Choose a title of 1–120 characters.')
    result = value.strip()
    if any(ord(ch) < 32 for ch in result):
        raise ValueError('The title cannot contain control characters.')
    return result


def document(value, format='md'):
    if format not in ('md', 'txt', 'docx', 'pdf'):
        raise ValueError('Choose md, txt, docx or pdf.')
    if not isinstance(value, str) or not value.strip() or len(value) > 30000:
        raise ValueError('Document text must be 1–30,000 characters.')
    return value.strip(), format


def _json(value):
    if isinstance(value, str):
        if len(value) > 60000:
            raise ValueError('Structured content is too large (60 KB maximum).')
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ValueError('Enter valid JSON content.') from exc
    if len(json.dumps(value, ensure_ascii=False)) > 60000:
        raise ValueError('Structured content is too large (60 KB maximum).')
    return value


def slides(value):
    value = _json(value)
    if not isinstance(value, list) or not 1 <= len(value) <= 15:
        raise ValueError('Provide 1–15 slides as a JSON array.')
    clean = []
    for slide in value:
        if not isinstance(slide, dict) or not isinstance(slide.get('title'), str) or not 1 <= len(slide['title'].strip()) <= 120:
            raise ValueError('Each slide needs a title of at most 120 characters.')
        bullets = slide.get('bullets', [])
        if not isinstance(bullets, list) or len(bullets) > 6 or any(not isinstance(b, str) or not 1 <= len(b.strip()) <= 160 for b in bullets):
            raise ValueError('Use up to six bullet strings per slide, each at most 160 characters.')
        clean.append({'title': slide['title'].strip(), 'bullets': [b.strip() for b in bullets]})
    return clean


def sheet(headers, rows):
    headers, rows = _json(headers), _json(rows)
    if not isinstance(headers, list) or not 1 <= len(headers) <= 20 or any(not isinstance(h, str) or not 1 <= len(h.strip()) <= 80 for h in headers):
        raise ValueError('Provide 1–20 short column headers as a JSON array.')
    if len({h.strip().casefold() for h in headers}) != len(headers):
        raise ValueError('Column headers must be unique.')
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError('Provide at most 200 rows as a JSON array.')
    clean_rows = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            raise ValueError('Every row must have the same number of cells as the headers.')
        clean = []
        for cell in row:
            if cell is None or type(cell) in (bool, int, float) or isinstance(cell, str):
                if isinstance(cell, str) and len(cell) > 250:
                    raise ValueError('Each text cell must be at most 250 characters.')
                if type(cell) is int and abs(cell) > 10**15:
                    raise ValueError('Numeric cells must be within supported spreadsheet bounds.')
                if type(cell) is float:
                    import math
                    if not math.isfinite(cell) or abs(cell) > 10**15:
                        raise ValueError('Numeric cells must be finite and within supported bounds.')
                clean.append(cell)
            else:
                raise ValueError('Cells may contain text, numbers, booleans or null only.')
        clean_rows.append(clean)
    if len(json.dumps({'headers': headers, 'rows': clean_rows}, ensure_ascii=False)) > 60000:
        raise ValueError('Spreadsheet content is too large (60 KB maximum).')
    return [h.strip() for h in headers], clean_rows


def filename(value, format):
    stem = re.sub(r'[^A-Za-z0-9._-]+', '_', title(value)).strip('._')[:90] or 'ora-file'
    return stem + '.' + format


def record_text(kind, content):
    if kind == 'presentation':
        return '\n'.join(s['title'] + '\n' + '\n'.join(s['bullets']) for s in content)
    if kind == 'spreadsheet':
        return '\n'.join([', '.join(content['headers'])] + [', '.join('' if cell is None else str(cell) for cell in row) for row in content['rows']])[:30000]
    return content


def metadata(record):
    return {k: record[k] for k in ('id', 'name', 'created_at')} | {
        'kind': record.get('kind', 'document'), 'format': record.get('format', 'md' if record['name'].lower().endswith('.md') else 'txt'),
        'version': record.get('version', 1),
    }


def _docx(record):
    from docx import Document
    from docx.shared import Inches
    doc = Document()
    section = doc.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.8)
    doc.add_heading(record.get('title', record['name']), 0)
    for line in record['text'].splitlines():
        if line.startswith('#') and line.lstrip('#').startswith(' '):
            doc.add_heading(line.lstrip('#').strip(), min(len(line) - len(line.lstrip('#')), 3))
        elif line.startswith(('- ', '* ')):
            doc.add_paragraph(line[2:], style='List Bullet')
        elif line.strip():
            doc.add_paragraph(line)
        else:
            doc.add_paragraph('')
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def _pdf(record):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    output = io.BytesIO()
    story = []
    styles = getSampleStyleSheet()
    story.append(Paragraph(escape(record.get('title', record['name'])), styles['Title']))
    story.append(Spacer(1, 14))
    for line in record['text'].splitlines():
        if line.startswith('#') and line.lstrip('#').startswith(' '):
            level = min(len(line) - len(line.lstrip('#')), 3)
            story.append(Paragraph(escape(line.lstrip('#').strip()), styles[f'Heading{level}']))
        elif line.startswith(('- ', '* ')):
            story.append(Paragraph('• ' + escape(line[2:]), styles['BodyText']))
        elif line.strip():
            story.append(Paragraph(escape(line), styles['BodyText']))
        else:
            story.append(Spacer(1, 8))
    SimpleDocTemplate(output, pagesize=(595, 842), rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54,
                      title=record.get('title', record['name'])).build(story)
    return output.getvalue()


def _pptx(record):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    for index, item in enumerate(record['content']):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(16, 25, 42)
        accent = slide.shapes.add_shape(1, Inches(0.7), Inches(0.75), Inches(0.12), Inches(0.55))
        accent.fill.solid()
        accent.fill.fore_color.rgb = RGBColor(66, 216, 224)
        accent.line.fill.background()
        heading = slide.shapes.add_textbox(Inches(1.0), Inches(0.7), Inches(11.5), Inches(0.85)).text_frame
        heading.text = item['title']
        heading.paragraphs[0].font.size = Pt(30)
        heading.paragraphs[0].font.bold = True
        heading.paragraphs[0].font.color.rgb = RGBColor(243, 248, 252)
        body = slide.shapes.add_textbox(Inches(1.05), Inches(1.9), Inches(11.1), Inches(4.9)).text_frame
        body.word_wrap = True
        for n, bullet in enumerate(item['bullets']):
            p = body.paragraphs[0] if n == 0 else body.add_paragraph()
            p.text = '•  ' + bullet
            p.font.size = Pt(23 if len(item['bullets']) <= 4 else 19)
            p.font.color.rgb = RGBColor(225, 235, 241)
            p.space_after = Pt(17 if len(item['bullets']) <= 4 else 11)
        footer = slide.shapes.add_textbox(Inches(0.8), Inches(7.02), Inches(11.8), Inches(0.25)).text_frame
        footer.text = f"{record.get('title', 'ORA')}  ·  {index + 1} / {len(record['content'])}"
        footer.paragraphs[0].alignment = PP_ALIGN.RIGHT
        footer.paragraphs[0].font.size = Pt(10)
        footer.paragraphs[0].font.color.rgb = RGBColor(137, 162, 180)
    output = io.BytesIO()
    prs.save(output)
    return output.getvalue()


def _xlsx(record):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = 'ORA data'
    content = record['content']
    ws.append(content['headers'])
    for cell in ws[1]:
        cell.data_type = 's'
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='17324D')
        cell.alignment = Alignment(wrap_text=True)
    for row in content['rows']:
        ws.append(row)
        for cell in ws[ws.max_row]:
            # Treat user and web-sourced strings as literal text, never formulas.
            if isinstance(cell.value, str):
                cell.data_type = 's'
    for i, header in enumerate(content['headers'], 1):
        ws.column_dimensions[get_column_letter(i)].width = min(40, max(14, len(header) + 5))
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def render(record):
    kind, fmt = record.get('kind', 'document'), record.get('format')
    if kind == 'presentation':
        fmt, data = 'pptx', _pptx(record)
    elif kind == 'spreadsheet':
        fmt, data = 'xlsx', _xlsx(record)
    elif fmt == 'docx':
        data = _docx(record)
    elif fmt == 'pdf':
        data = _pdf(record)
    else:
        fmt = fmt if fmt in ('md', 'txt') else 'txt'
        data = record['text'].encode('utf-8')
    if len(data) > 3_000_000:
        raise ValueError('Rendered file exceeds the 3 MB download limit.')
    return data, MIME[fmt], filename(record.get('title', record['name'].rsplit('.', 1)[0]), fmt)
