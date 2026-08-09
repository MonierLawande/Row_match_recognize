# Arabic Pages — Reproducible Source

Editable source and build script for the thesis's **Arabic abstract + Arabic
title page**, produced as `arabic_pages_final.pdf`.

This exists because the first `thesis/arabic_pages.pdf` was a LibreOffice
export with no editable source in the repository and contained outdated
benchmark numbers. This directory now regenerates the active copy from a
plain-text, version-controllable source.

## Files

Two independent routes produce the same two pages. Maintain whichever you prefer.

**Route A — LibreOffice (original)**

| File | Purpose |
|------|---------|
| `arabic_pages.fodt` | Editable flat-ODT source (plain-text XML; page 1 = abstract, page 2 = title page) |
| `build.sh` | Build script (fails clearly if a tool/font is missing) |
| **`arabic_pages_final.pdf`** | Output |

**Route B — LaTeX**

| File | Purpose |
|------|---------|
| `arabic_pages.tex` | Editable LaTeX source (XeLaTeX; all sizes and spacing as named macros at the top) |
| `nu-logo.png` | University logo, extracted from the `.fodt` |
| `build_latex.sh` | Build script |
| `arabic_pages_latex.pdf` | Output |

## Which file to submit
- ✅ **`thesis/arabic_pages.pdf` is the active corrected file**, identical
  to `arabic_pages_final.pdf`: author-approved title, benchmark means
  0.17 / 1.04 / 1.98 s, scalability to 227.9 M, and «أنماط التخطي».

## Intentional English↔Arabic title difference
The Arabic title is the **author-approved wording**, deliberately not a literal
translation of the English title. This is intentional and must **not** be treated
as a translation inconsistency:
- English: *Row Pattern Matching Analytics: Bringing SQL MATCH_RECOGNIZE to Pandas DataFrames*
- Arabic (2 lines): استخراج أنماط السجلات التسلسلية / تعزيز إطارات بيانات بانداس بتنفيذ آلية التعرف على الأنماط

## Arabic title (final, applied 2026-07-25)
Two centered lines:
> استخراج أنماط السجلات التسلسلية
> تعزيز إطارات بيانات بانداس بتنفيذ آلية التعرف على الأنماط

## Build

```bash
cd thesis/arabic_pages_source

./build.sh          # Route A -> arabic_pages_final.pdf
./build_latex.sh    # Route B -> arabic_pages_latex.pdf
```

Both produce 2 A4 pages.

### LaTeX route notes

- **Engine:** XeLaTeX. `pdflatex` cannot do Arabic — it cannot load system
  fonts. `build_latex.sh` auto-detects a TeX Live under `$HOME` and falls back
  to whatever `xelatex` is on `PATH`.
- **Toolchain:** TeX Live **2026** installed at `~/texlive/2026`
  (scheme-medium, no sudo, `PATH` deliberately not modified). Ubuntu 24.04 is
  frozen on TeX Live 2023 and Debian blocks `tlmgr` from updating the system
  tree, so a home install is the only route to a current kernel.
  `bidi` and `zref` were added with `tlmgr install bidi zref`.
- **Do not use the system `/usr/bin/xelatex`** (TeX Live 2023): Debian does not
  ship `bidi`, so it cannot build this file.
- **Kernel shim.** Section 0 of `arabic_pages.tex` defines `\IfClassLoadedT` /
  `\IfFileLoadedTF`, which `bidi` needs and which entered the LaTeX kernel in
  2024. It is written with `\providecommand`, so it is **inert on TeX Live 2026**
  (kernel `2026-06-01`) — verified by building with the block deleted. It is kept
  only for portability to older kernels; deleting it is safe here.
- **Line spacing.** LibreOffice's "132%" multiplies Amiri's *full line box*, not
  the font size. The `\fontsize{14pt}{29pt}` values reproduce that; `\setstretch`
  is therefore left at `1.0` so the spacing is not counted twice.

### Overleaf

Works as-is, with three steps:

1. **Menu → Settings → Compiler → XeLaTeX.** Overleaf does *not* reliably honour
   the `% !TEX program` magic comment; setting it here is what matters.
2. Upload `nu-logo.png` next to the `.tex`.
3. **Upload** the `.tex` rather than copy-pasting — pasting can mangle Arabic
   diacritics and character order.

Overleaf already provides `bidi`, `polyglossia`, and Amiri, and its kernel is
modern, so the shim disables itself.

## Method / environment (recorded for reproducibility)
- **Tool:** LibreOffice headless (`soffice --headless --convert-to pdf`). This is
  the same engine that produced the original PDF (LibreOffice 24.2), and it shapes
  Arabic via HarfBuzz with correct RTL/bidi. Version: `soffice --version`.
- **Source format:** flat OpenDocument Text (`.fodt`) — a single, human-editable
  XML file, so the Arabic content is version-controllable (unlike a binary PDF).
- **Font:** **Amiri** (Naskh; confirmed via `fc-list`). The style also names
  *Noto Naskh Arabic* as a fallback; *Scheherazade* is another option. Edit the
  `<style:font-face>` / `style:font-name-complex` entries in `arabic_pages.fodt`
  to switch fonts.
- **Numerals:** Western digits typed directly (matching the English thesis).
- **Page:** A4; 1.5-in left margin and 1-in top, right, and bottom
  margins; RTL (`style:writing-mode="rl-tb"`).

Note on engines: `lualatex` on this machine is missing `luaotfload` (the Unicode
font loader), so it cannot load system Arabic fonts. `xelatex` **is** available
(`/usr/bin/xelatex` from `texlive-binaries`) and is what Route B uses.

Do **not** download or bundle font files; only installed system fonts are used.

## Content provenance (verified against the final English thesis)
- Benchmark means: engine **0.17 s**, Oracle 21c EE **1.04 s**, Trino **1.98 s**
  (rounded values from the 30-cell cross-system matrix).
- Engine fastest in **all 30** normal cross-system cells.
- Scalability up to **227.9 million** rows (Amazon Reviews 2023).
- Terminology: **أنماط التخطي** (skip *modes*), not «سياسات التخطي».
- Title-page fields copied from the English title page (`Thesis.tex`):
  Nile University · School of IT & CS · Program of Informatics · MSc in
  Informatics · Monier Ashraf Monier Lawande · Prof. Mohamed ElHelw ·
  Prof. Ahmed Awad · August 2026.

## Submission note
The workflow keeps the Arabic pages as a standalone PDF; they are not
`\includepdf`'d into `Thesis.tex`. Submit `thesis/arabic_pages.pdf` with
the English thesis, or merge it into the final PDF if the deposit requires
one file. The build script does not modify `Thesis.pdf`.
