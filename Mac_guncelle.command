#!/bin/bash
cd "$(dirname "$0")" || exit 1
VPY="./.venv/bin/python"; [ -x "$VPY" ] || VPY="$(command -v python3)"
"$VPY" guncelle.py
read -r -p "Kapatmak için Enter..." _
