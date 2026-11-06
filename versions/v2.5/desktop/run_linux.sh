#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
  echo 'Tk is missing. On Debian/Ubuntu install python3-tk and python3-venv.' >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'import PIL, numpy, cryptography, reedsolo' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python binary_image_passcode.py "$@"
