#!/usr/bin/env bash
# ============================================================
# Build arabic_pages_latex.pdf from arabic_pages.tex
# Engine: XeLaTeX (required — Arabic needs system font loading)
#
# This is the LaTeX route.  build.sh is the original LibreOffice
# route; both produce the same two pages.  Use whichever you
# prefer to maintain.
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="arabic_pages.tex"
OUT="arabic_pages_latex.pdf"
cd "$HERE"

# --- 1. Required engine ---------------------------------------------------
# Prefer a TeX Live installed under $HOME: it carries a modern LaTeX kernel
# and ships `bidi`, which Debian's texlive-latex-extra does not.  Fall back to
# whatever xelatex is on PATH.
XELATEX=""
for candidate in "$HOME"/texlive/*/bin/*/xelatex; do
  [ -x "$candidate" ] && XELATEX="$candidate"
done
if [ -z "$XELATEX" ] && command -v xelatex >/dev/null 2>&1; then
  XELATEX="$(command -v xelatex)"
fi
if [ -z "$XELATEX" ]; then
  echo "ERROR: xelatex not found." >&2
  echo "       Either install TeX Live under \$HOME, or:" >&2
  echo "         sudo apt install texlive-xetex" >&2
  exit 1
fi
echo "Engine: $XELATEX"

# --- 2. Required source and logo -----------------------------------------
for f in "$SRC" nu-logo.png; do
  if [ ! -f "$f" ]; then
    echo "ERROR: required file $f not found." >&2
    exit 1
  fi
done

# --- 3. Required font: Amiri ---------------------------------------------
if [ "$(fc-list | grep -ci 'Amiri' || true)" -eq 0 ]; then
  echo "ERROR: the Amiri font is not installed." >&2
  echo "       Install it with:  sudo apt install fonts-hosny-amiri" >&2
  exit 1
fi

# --- 4. Compile in an isolated directory ---------------------------------
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

echo "Rendering $OUT with xelatex ..."
# Two passes so any future cross-references settle.
for pass in 1 2; do
  "$XELATEX" -interaction=nonstopmode -halt-on-error \
          -output-directory="$BUILD" "$SRC" >"$BUILD/pass$pass.log" 2>&1 || {
    echo "ERROR: xelatex failed on pass $pass. Last lines:" >&2
    tail -30 "$BUILD/pass$pass.log" >&2
    exit 1
  }
done

cp "$BUILD/${SRC%.tex}.pdf" "$HERE/$OUT"

if [ -f "$OUT" ]; then
  PAGES="$(pdfinfo "$OUT" 2>/dev/null | awk '/^Pages/{print $2}')"
  echo "OK: wrote $HERE/$OUT${PAGES:+ ($PAGES pages)}"
else
  echo "ERROR: compilation produced no PDF." >&2
  exit 1
fi
