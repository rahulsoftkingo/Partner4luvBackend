from fpdf import FPDF
from pathlib import Path
import textwrap

md_path = Path('PROJECT_DOCUMENTATION.md')
pdf_path = Path('PROJECT_DOCUMENTATION.pdf')
text = md_path.read_text(encoding='utf-8')

pdf = FPDF(unit='mm', format='A4')
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()
pdf.set_font('Arial', '', 12)

for line in text.splitlines():
    pdf.set_x(pdf.l_margin)
    if line.startswith('# '):
        pdf.set_font('Arial', 'B', 18)
        pdf.multi_cell(0, 10, line[2:].strip())
        pdf.ln(2)
        pdf.set_font('Arial', '', 12)
    elif line.startswith('## '):
        pdf.set_font('Arial', 'B', 14)
        pdf.multi_cell(0, 8, line[3:].strip())
        pdf.ln(1)
        pdf.set_font('Arial', '', 12)
    elif line.startswith('### '):
        pdf.set_font('Arial', 'B', 12)
        pdf.multi_cell(0, 8, line[4:].strip())
        pdf.set_font('Arial', '', 12)
    elif line.startswith('- '):
        wrapped = textwrap.wrap(line[2:].strip(), width=100)
        for i, w in enumerate(wrapped):
            prefix = '- ' if i == 0 else '  '
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, prefix + w)
    elif line.strip() == '':
        pdf.ln(2)
    else:
        wrapped = textwrap.wrap(line.strip(), width=100)
        for w in wrapped:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, w)

pdf.output(pdf_path)
print(f'Generated {pdf_path}')
