#!/usr/bin/env python3
"""PDF -> raw text dump (x<TAB>y<TAB>text, pages split by #P<n>), same shape the
browser pdf.js dump produced.  y is measured from the page bottom.
Usage: python extract.py "pdf/NCAA 1929.pdf" > raw/NCAA1929.txt"""
import sys, pdfplumber

with pdfplumber.open(sys.argv[1]) as pdf:
    for n, page in enumerate(pdf.pages, start=1):
        print(f'#P{n}')
        H = page.height
        # group characters into runs: same line (baseline) and small x gap
        words = page.extract_words(keep_blank_chars=True, x_tolerance=2.5, y_tolerance=2,
                                   use_text_flow=False, extra_attrs=['size'])
        items = []
        for w in words:
            s = ' '.join(w['text'].split())
            if not s or s.startswith('Compiled by'):
                continue
            items.append([round(w['x0']), H - w['bottom'], s])
        # snap near-equal baselines (+-2pt) to one y so rows line up
        items.sort(key=lambda i: -i[1])
        ref = None
        for it in items:
            if ref is None or ref - it[1] > 2:
                ref = it[1]
            it[1] = round(ref)
        for x, y, s in items:
            print(f"{x}\t{y}\t{s}")
