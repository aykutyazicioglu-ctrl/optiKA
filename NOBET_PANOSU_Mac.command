#!/bin/bash
# =====================================================================
#  optiKA Nöbet Panosu v1.0.0 — TEK DOSYA (Mac)
#  İlk çalıştırmada kurar (Python ortamı, otomatik güncelleme, masaüstünde "Nöbet Panosu" uygulaması),
#  sonraki her açılışta: güncel listeyi alır + panoyu açar.
#  İlk sefer: sağ tık > Aç.  Sonra masaüstündeki "Nöbet Panosu" simgesini kullanın.
#  Yeniden kurmak için Terminal'de:  bash NOBET_PANOSU_Mac.command kur
# =====================================================================
SURUM=5
ARALIK=5          # görev kaç dakikada bir uyansın; oda sitesine yalnızca 08:30 ve 18:00'de gidilir (guncelle.py PLAN)

cd "$(dirname "$0")" || exit 1
DIZIN="$(pwd)"
BU="$DIZIN/$(basename "$0")"
AJAN="$HOME/Library/LaunchAgents"
GOREV="$AJAN/com.optika.nobetpanosu.guncelle.plist"
OTO="$AJAN/com.optika.nobetpanosu.pano.plist"
UYGULAMA="$HOME/Desktop/Nöbet Panosu.app"
bekle() { [ -t 0 ] && read -r -p "$1" _; }

kurulum() {
  echo "optiKA Nöbet Panosu kuruluyor (ilk çalıştırma, 1-2 dakika sürer) — $DIZIN"
  xattr -dr com.apple.quarantine "$DIZIN" 2>/dev/null
  chmod +x "$DIZIN"/*.command 2>/dev/null

  PY="$(command -v python3)"
  [ -x /usr/local/bin/python3 ] && PY=/usr/local/bin/python3
  [ -x /opt/homebrew/bin/python3 ] && PY=/opt/homebrew/bin/python3
  if [ -z "$PY" ] || ! "$PY" -c "import sys; assert sys.version_info >= (3, 8)" 2>/dev/null; then
    echo; echo "[HATA] Python 3 bulunamadı. https://www.python.org/downloads/macos/ adresinden kurup bu dosyayı tekrar açın."
    bekle "Kapatmak için Enter..."; return 1
  fi
  echo "Python ortamı hazırlanıyor..."
  "$PY" -m venv "$DIZIN/.venv" || { echo "[HATA] Python ortamı oluşturulamadı."; bekle "Enter..."; return 1; }
  "$DIZIN/.venv/bin/python" -m pip install --disable-pip-version-check -q requests beautifulsoup4 segno || {
    echo "[HATA] Paketler kurulamadı (internet bağlantısını kontrol edin)."; bekle "Enter..."; return 1; }
  VPY="$DIZIN/.venv/bin/python"

  # Otomatik güncelleme (launchd): 5 dk'da bir uyanır, siteye yalnızca plan saatlerinde gider
  mkdir -p "$AJAN"
  cat > "$GOREV" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.optika.nobetpanosu.guncelle</string>
  <key>ProgramArguments</key><array>
    <string>$VPY</string><string>$DIZIN/guncelle.py</string><string>--zamanli</string><string>--aralik</string><string>$ARALIK</string>
  </array>
  <key>WorkingDirectory</key><string>$DIZIN</string>
  <key>StartInterval</key><integer>$((ARALIK * 60))</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>$DIZIN/guncelle_hata.log</string>
</dict></plist>
PLIST
  launchctl bootout "gui/$(id -u)" "$GOREV" 2>/dev/null
  launchctl bootstrap "gui/$(id -u)" "$GOREV" 2>/dev/null || launchctl load -w "$GOREV"

  # Oturum açılınca pano kendiliğinden başlasın (bir sonraki oturumda devreye girer; şimdi zaten açılıyor)
  launchctl bootout "gui/$(id -u)" "$OTO" 2>/dev/null
  cat > "$OTO" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.optika.nobetpanosu.pano</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$BU</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST

  # Masaüstünde tek tıkla açılan "Nöbet Panosu" uygulaması (Terminal penceresi açmaz).
  # Aynı uygulama panodaki "Şimdi güncelle" / "Saatleri kaydet" düğmelerinin nobetpanosu:// bağlantısını karşılar.
  rm -rf "$UYGULAMA"
  osacompile -o "$UYGULAMA" \
    -e 'on run' \
    -e "  do shell script \"/bin/bash \" & quoted form of \"$BU\" & \" >/dev/null 2>&1 &\"" \
    -e 'end run' \
    -e 'on open location adres' \
    -e "  do shell script quoted form of \"$VPY\" & \" \" & quoted form of \"$DIZIN/guncelle.py\" & \" --ilerleme \" & quoted form of adres & \" >/dev/null 2>&1 &\"" \
    -e 'end open location' 2>/dev/null
  if [ -d "$UYGULAMA" ]; then
    cp "$DIZIN/simge/optika.icns" "$UYGULAMA/Contents/Resources/applet.icns" 2>/dev/null
    PB=/usr/libexec/PlistBuddy; IP="$UYGULAMA/Contents/Info.plist"
    $PB -c "Delete :CFBundleURLTypes" "$IP" 2>/dev/null
    $PB -c "Add :CFBundleURLTypes array" -c "Add :CFBundleURLTypes:0 dict" \
        -c "Add :CFBundleURLTypes:0:CFBundleURLName string com.optika.nobetpanosu" \
        -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" \
        -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string nobetpanosu" "$IP" 2>/dev/null
    $PB -c "Set :CFBundleIdentifier com.optika.nobetpanosu" "$IP" 2>/dev/null || $PB -c "Add :CFBundleIdentifier string com.optika.nobetpanosu" "$IP" 2>/dev/null
    codesign --force --deep -s - "$UYGULAMA" >/dev/null 2>&1      # simge/Info.plist değişti: yerel imzayı yenile
    touch "$UYGULAMA"
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$UYGULAMA" >/dev/null 2>&1
  fi

  # Pano ekranı kararmasın: ekran koruyucu kapalı, ekran/bilgisayar uykusu kapalı (adaptördeyken)
  defaults -currentHost write com.apple.screensaver idleTime -int 0 2>/dev/null
  echo "Ekran ve bilgisayar uykusu kapatılıyor (Mac şifreniz istenebilir; istemezseniz Enter'a basıp geçin)..."
  if [ -t 0 ]; then sudo -p "Mac şifreniz: " pmset -c displaysleep 0 sleep 0 2>/dev/null; fi

  echo; echo "=========================================="
  "$VPY" "$DIZIN/guncelle.py" --kod
  echo "Bu kodu lisans için optiKA'ya iletin."
  echo "=========================================="
  echo "1" > "$DIZIN/.kurulum_surum_$SURUM"
  echo; echo "Kurulum tamam. Bundan sonra masaüstündeki \"Nöbet Panosu\" simgesini kullanın."
  echo "Ekran hâlâ kararırsa: Sistem Ayarları > Kilit Ekranı > 'Ekran koruyucuyu başlat' ve 'Ekranı kapat' -> Hiçbir zaman."
  echo "Pano şimdi açılıyor..."; sleep 4
}

if [ "$1" = "kur" ] || [ ! -f "$DIZIN/.kurulum_surum_$SURUM" ] || [ ! -x "$DIZIN/.venv/bin/python" ] || [ ! -f "$GOREV" ]; then
  kurulum || exit 1
fi
VPY="$DIZIN/.venv/bin/python"

# 1) Güncel listeyi arka planda al: pano giriş ekranında % çubuğu olarak gösterir
nohup "$VPY" "$DIZIN/guncelle.py" --ilerleme >/dev/null 2>&1 &
# Panodaki "Şimdi güncelle" düğmesi için yerel yardımcı (yalnızca bu bilgisayar): eskisini kapat, bu klasörden yenisini başlat
pkill -f "guncelle.py --yardimci" 2>/dev/null; sleep 0.3
nohup "$VPY" "$DIZIN/guncelle.py" --yardimci >/dev/null 2>&1 &

# Pano açıkken ekran/bilgisayar uyumasın
pkill -f "caffeinate -dimsu" 2>/dev/null; nohup caffeinate -dimsu >/dev/null 2>&1 &

# 2) Panoyu aç: Chrome, yoksa Edge (normal pencere; F = tam ekran aç/kapat, A = ilçe seçimi)
SAYFA="file://$("$VPY" -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$DIZIN/nobet_panosu.html")"
for TARAYICI in "Google Chrome" "Microsoft Edge"; do
  if open -Ra "$TARAYICI" 2>/dev/null; then
    open -na "$TARAYICI" --args --app="$SAYFA" --start-maximized --no-first-run --noerrdialogs \
      --disable-session-crashed-bubble --disable-features=Translate --user-data-dir="$DIZIN/tarayici_profil"
    # Pencereyi öne al ve F13 gönder: pano kayıtlı tercihe göre tam ekrana geçer
    # (macOS "Erişilebilirlik" izni isteyebilir; izin yoksa panoya bir tık / F tuşu yeterli)
    ( sleep 6; osascript -e "tell application \"$TARAYICI\" to activate" -e 'tell application "System Events" to key code 105' ) >/dev/null 2>&1 &
    exit 0
  fi
done
open "$DIZIN/nobet_panosu.html"     # Chrome/Edge yoksa varsayılan tarayıcı
