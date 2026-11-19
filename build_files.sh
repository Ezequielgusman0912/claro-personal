#!/bin/bash
set -e
npm ci --ignore-scripts --no-audit --no-fund
npm run build:ocr
python3 -m pip install --break-system-packages -r requirements.txt
python3 manage.py collectstatic --noinput
