#!/usr/bin/env bash
# ============================================================
# Reproducible build for arabic_pages_final.pdf
# Engine: LibreOffice headless (soffice) rendering a flat-ODT (.fodt)
# LibreOffice shapes Arabic via HarfBuzz and handles RTL + bidi.
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="arabic_pages.fodt"
OUT="arabic_pages_final.pdf"
cd "$HERE"

# --- 1. Required tool: LibreOffice (soffice/libreoffice) -----------------
SOFFICE=""
for c in soffice libreoffice; do
  if command -v "$c" >/dev/null 2>&1; then SOFFICE="$c"; break; fi
done
if [ -z "$SOFFICE" ]; then
  echo "ERROR: LibreOffice (soffice/libreoffice) not found. Install libreoffice-writer." >&2
  exit 1
fi

# --- 2. Required source ---------------------------------------------------
if [ ! -f "$SRC" ]; then
  echo "ERROR: source $SRC not found." >&2
  exit 1
fi

# --- 3. Recommended font: Amiri (or Noto Naskh Arabic / Scheherazade) -----
# grep -c reads the whole stream (no SIGPIPE under pipefail).
ARFONT="$(fc-list | grep -ciE 'Amiri|Noto Naskh Arabic|Scheherazade' || true)"
if [ "${ARFONT:-0}" -eq 0 ]; then
  echo "ERROR: no Arabic Naskh font (Amiri / Noto Naskh Arabic / Scheherazade) installed." >&2
  exit 1
fi

# --- 4. Convert to PDF (isolated profile so it works headless) ------------
PROFILE="$(mktemp -d)"
echo "Rendering $OUT with $SOFFICE (headless) ..."
"$SOFFICE" --headless --nologo --nofirststartwizard \
  -env:UserInstallation="file://$PROFILE" \
  --convert-to pdf --outdir "$HERE" "$SRC" >/dev/null
rm -rf "$PROFILE"

# LibreOffice writes <basename>.pdf; rename to the required output name.
if [ -f "arabic_pages.pdf" ]; then
  mv -f "arabic_pages.pdf" "$OUT"
fi

if [ -f "$OUT" ]; then
  echo "OK: wrote $HERE/$OUT"
else
  echo "ERROR: conversion produced no PDF." >&2
  exit 1
fi

