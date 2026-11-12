#!/bin/bash
cd "$(dirname "$0")" || exit 1
VPY="./.venv/bin/python"; [ -x "$VPY" ] || VPY="$(command -v python3)"
echo; "$VPY" guncelle.py --kod
echo; echo "Bu kodu optiKA'ya iletin (lisans bu bilgisayara bağlanır)."
read -r -p "Kapatmak için Enter..." _
