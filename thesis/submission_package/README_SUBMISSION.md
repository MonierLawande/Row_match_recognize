# Committee Submission Package

**Prepared:** 2026-09-12 · **Git commit:** `704335278162ea790983f7d1f37c21f50e364c67` (front-matter changes still uncommitted in the working tree)

| File | Content | Pages | SHA-256 |
|------|---------|-------|---------|
| `Thesis.pdf` | English thesis (cover → Appendix A) | **111** | `4a547c559f6b34409cad5a52c228950b6f8848991de175dce56d157e55b8f5c7` |
| `thesis_Monier_lawande.pdf` | Merged deposit copy (English + Arabic back matter) | **114** | `4975e941eb3bd3451ca2c4a435202acdfc166911016b0c47f924c6eaab06dbef` |
| `arabic_pages.pdf` | Arabic abstract (p.1), Arabic title page (p.2), Arabic cover (p.3) | **3** | `f2be7c57e5ace8e012d1b131f780136234bb9516a323ae9c8c35070b3914b683` |
| `cover.pdf` | English front cover (p.1) and Arabic back cover (p.2) | **2** | `6208f821df9480915f5ccd86e46aa98296789f9bea89db8f22ab78276df74782` |

## Front matter (NU Thesis Template Version 2026)
Cover · Title page · Certification of Approval (signed) · Copyright (i) ·
Acknowledgement (ii) · Declaration (iii) · Abstract (iv–v) · Table of Contents (vi) ·
List of Figures · List of Tables · List of Symbols · List of Publications · Chapter 1 (p.1).
The Arabic back matter follows the template order: الملخص · صفحة العنوان ولجنة الإشراف · الغلاف.
The Arabic approval page is intentionally omitted.

## Test result
`python -m pytest -q` from the repository root → **709 passed** (0 failed), exit 0.
The suite now collects 741 tests; the extra 32 are `tests/test_order_by_expressions.py`,
added after the recorded validation run.

## Verified consistency (English ↔ Arabic)
- Benchmark values match in both: engine **0.17 s**, Oracle **1.04 s**, Trino **1.98 s**;
  30 cross-system cells; 35/35 and 33/35 stress cells; scalability to **227.9 M** rows.
- Both title pages carry the same committee: Professor Mohamed ElHelw (Nile University)
  and Associate Professor Ahmed Awad (The British University in Dubai, and Cairo University).
- Submission date on both covers: **SEPTEMBER/2026** · **سبتمبر/2026**.

## Provenance of the results
Engine figures were measured on commit `f8b052d` (identical `src/` and `tests/` trees to the
recorded campaign commit), across four campaigns under one protocol: dedicated control group,
1 CPU, 32 GB (58 GB for the scalability sweep), 5 warm-ups + 20 measured runs,
1.5× IQR filtering. Oracle and Trino values were retained from protocol-aligned campaigns.

## Notes
- The Arabic pages are built by `../arabic_pages_source/make_arabic_pdf.py` from `arabic_pages.fodt`.
  They keep the Amiri face of the earlier approved version, laid out to the template's positions;
  the glyphs are vector outlines with an invisible Unicode text layer, so the pages print exactly
  like the template and remain fully searchable.
- The Arabic abstract is 289 words, right-aligned rather than justified: LibreOffice
  inserts kashida stretching inside words when justifying Arabic, which breaks text search., within the template's 250–300 range.
