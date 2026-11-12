#!/bin/bash
# Otomatik güncelleme, açılışta başlatma ve masaüstü simgesini kaldırır (pano dosyaları silinmez)
cd "$(dirname "$0")" || exit 1
for G in guncelle pano; do
  P="$HOME/Library/LaunchAgents/com.optika.nobetpanosu.$G.plist"
  launchctl bootout "gui/$(id -u)" "$P" 2>/dev/null || launchctl unload -w "$P" 2>/dev/null
  rm -f "$P"
done
rm -rf "$HOME/Desktop/Nöbet Panosu.app" .kurulum_surum_*
pkill -f "caffeinate -dimsu" 2>/dev/null
echo "Otomatik görevler ve masaüstü simgesi kaldırıldı."; read -r -p "Kapatmak için Enter..." _
