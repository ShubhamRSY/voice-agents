#!/bin/bash
# Generate PDF from the HTML technical document
# Requires: weasyprint (pip install weasyprint)
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v weasyprint &> /dev/null; then
  echo "Installing weasyprint..."
  pip install weasyprint -q
fi

echo "Generating PDF..."
weasyprint index.html NEXUS_Technical_Architecture_v2.0.pdf

echo "Done: NEXUS_Technical_Architecture_v2.0.pdf"
ls -lh *.pdf
