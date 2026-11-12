#!/bin/bash
cd "$(dirname "$0")"
echo "===== NOBET PANOSU DURUM KONTROLU ====="
echo
echo "--- Otomatik guncelleme gorevi ---"
launchctl list | grep -i nobetpanosu || echo "[HATA] Gorev yuklu degil. Mac_kurulum.command calistirin."
echo
echo "--- Son kayitlar (guncelle.log) ---"
[ -f guncelle.log ] && tail -n 12 guncelle.log || echo "guncelle.log yok - guncelleme hic calismamis."
echo
echo "--- Simdi elle guncelleniyor ---"
if [ -x .venv/bin/python ]; then .venv/bin/python guncelle.py; else python3 guncelle.py; fi
echo
echo "Bu pencerenin ekran goruntusunu optiKA ya gonderebilirsiniz."
read -n 1 -s -r -p "Kapatmak icin bir tusa basin..."
