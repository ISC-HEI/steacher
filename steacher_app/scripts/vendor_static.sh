#!/usr/bin/env bash
set -euo pipefail

# Simple vendor script: copy specific third‑party files from node_modules
# into steacher_app/static/vendor so collectstatic can hash and serve them.
# Usage: bash steacher_app/scripts/vendor_static.sh

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="${APP_DIR}/node_modules"
DEST_DIR="${APP_DIR}/static/vendor"

# Create destination directories
mkdir -p \
  "${DEST_DIR}/vue/dist" \
  "${DEST_DIR}/@electric-sql/pglite/dist" \
  "${DEST_DIR}/canvas-confetti/dist" \
  "${DEST_DIR}/marked/lib" \
  "${DEST_DIR}/dompurify/dist" \
  "${DEST_DIR}/prismjs/components" \
  "${DEST_DIR}/prismjs/themes" \
  "${DEST_DIR}/bulma/css" \
  "${DEST_DIR}/@fortawesome/fontawesome-free/css" \
  "${DEST_DIR}/@fortawesome/fontawesome-free" \
  "${DEST_DIR}/pyodide"

# Vue (ESM browser build)
cp -f "${SRC_DIR}/vue/dist/vue.esm-browser.js" "${DEST_DIR}/vue/dist/"

# PGlite (Electric SQL)
cp -f "${SRC_DIR}/@electric-sql/pglite/dist/index.js" "${DEST_DIR}/@electric-sql/pglite/dist/"

# canvas-confetti (ES module)
cp -f "${SRC_DIR}/canvas-confetti/dist/confetti.module.mjs" "${DEST_DIR}/canvas-confetti/dist/"

# marked (ES module)
cp -f "${SRC_DIR}/marked/lib/marked.esm.js" "${DEST_DIR}/marked/lib/"

# DOMPurify (ES module)
cp -f "${SRC_DIR}/dompurify/dist/purify.es.mjs" "${DEST_DIR}/dompurify/dist/"

# Prism.js core + selected languages + theme
cp -f "${SRC_DIR}/prismjs/prism.js" "${DEST_DIR}/prismjs/"
cp -f "${SRC_DIR}/prismjs/themes/prism.min.css" "${DEST_DIR}/prismjs/themes/"
cp -f "${SRC_DIR}/prismjs/components/prism-clike.min.js" "${DEST_DIR}/prismjs/components/" || true
cp -f "${SRC_DIR}/prismjs/components/prism-java.min.js" "${DEST_DIR}/prismjs/components/" || true
cp -f "${SRC_DIR}/prismjs/components/prism-scala.min.js" "${DEST_DIR}/prismjs/components/" || true
cp -f "${SRC_DIR}/prismjs/components/prism-python.min.js" "${DEST_DIR}/prismjs/components/" || true
cp -f "${SRC_DIR}/prismjs/components/prism-sql.min.js" "${DEST_DIR}/prismjs/components/" || true

# Bulma CSS
cp -f "${SRC_DIR}/bulma/css/bulma.min.css" "${DEST_DIR}/bulma/css/"

# Font Awesome CSS + webfonts
cp -f "${SRC_DIR}/@fortawesome/fontawesome-free/css/all.min.css" "${DEST_DIR}/@fortawesome/fontawesome-free/css/"
cp -rf "${SRC_DIR}/@fortawesome/fontawesome-free/webfonts" "${DEST_DIR}/@fortawesome/fontawesome-free/"

# Pyodide (copy entire dir; required assets are co-located with pyodide.mjs)
if [ -d "${SRC_DIR}/pyodide" ]; then
  cp -rf "${SRC_DIR}/pyodide" "${DEST_DIR}/"
fi

echo "Vendor copy complete -> ${DEST_DIR}"
