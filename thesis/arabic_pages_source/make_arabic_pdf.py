#!/usr/bin/env python3
"""Build arabic_pages.pdf from arabic_pages.fodt.

The NU Thesis Template 2026 requires Arabic text in Calibri.  Calibri's Arabic
ligatures give a broken PDF text layer (the template's own Word export shows
the same corruption), so the pages are built in two layers:

  1. Visible layer  : LibreOffice export in Calibri / Times New Roman, then
                      Ghostscript converts the glyphs to vector outlines.
  2. Search layer   : the same document exported with Amiri (which yields a
                      correct Unicode text layer), made invisible (3 Tr) and
                      laid over the visible layer.

The result prints exactly like the Calibri pages and is fully searchable.
Requires: soffice, gs, PyMuPDF (fitz), Calibri installed for fontconfig.
"""
import os, re, shutil, subprocess, tempfile
import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'arabic_pages.fodt')
OUT = os.path.join(HERE, 'arabic_pages.pdf')

def export(fodt, outdir):
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', outdir, fodt],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.join(outdir, os.path.splitext(os.path.basename(fodt))[0] + '.pdf')

with tempfile.TemporaryDirectory() as tmp:
    visible = export(SRC, tmp)
    outlined = os.path.join(tmp, 'outlined.pdf')
    subprocess.run(['gs', '-q', '-o', outlined, '-sDEVICE=pdfwrite', '-dNoOutputFonts', visible], check=True)

    layer_dir = os.path.join(tmp, 'layer'); os.makedirs(layer_dir)
    s = open(SRC, encoding='utf-8').read()
    s = s.replace('font-name-complex="Calibri"', 'font-name-complex="Amiri"')
    s = s.replace('font-name-complex="Times New Roman"', 'font-name-complex="Amiri"')
    s = s.replace('fo:text-align="justify"', 'fo:text-align="start"')   # no kashida in the search layer
    layer_fodt = os.path.join(layer_dir, 'arabic_pages.fodt')
    open(layer_fodt, 'w', encoding='utf-8').write(s)
    layer = fitz.open(export(layer_fodt, layer_dir))
    for page in layer:
        for xref in page.get_contents():
            layer.update_stream(xref, re.sub(rb'(?<![A-Za-z])BT(?![A-Za-z])', b'BT 3 Tr', layer.xref_stream(xref)))
    inv = os.path.join(tmp, 'invisible.pdf'); layer.save(inv)

    vis = fitz.open(outlined); invd = fitz.open(inv)
    for i, page in enumerate(vis):
        page.show_pdf_page(page.rect, invd, i, overlay=True)
    vis.set_metadata({'title': 'Arabic back matter — Row Pattern Matching Analytics',
                      'author': 'Monier Ashraf Monier Lawande'})
    vis.save(OUT, garbage=3, deflate=True)
print('wrote', OUT)
