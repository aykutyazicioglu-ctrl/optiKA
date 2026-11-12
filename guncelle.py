# -*- coding: utf-8 -*-
"""
optiKA Nöbetçi Eczane Panosu - veri güncelleyici
Samsun Eczacı Odası sitesinden bugünkü nöbetçi eczaneleri çeker,
her eczane için yol tarifi QR kodu üretir ve nobet_veri.js dosyasına yazar.

Kurulum : pip install requests beautifulsoup4 segno
Kullanım: python guncelle.py              (siteden çeker)
          python guncelle.py --html x.html (kayıtlı sayfadan test)
"""
import sys, os, re, json, time, argparse
from datetime import datetime
from urllib.parse import unquote

KAYNAK = "https://www.samsuneczaciodasi.org.tr/nobetci-eczaneler"
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nobet_veri.js")
# Odanın sitesi yalnızca bu saatlerde sorgulanır (zamanlanmış görev --zamanli ile çalışır).
# Sabah saatinden sonra sitede bugünün listesi görünene kadar 5 dakikada bir yeniden denenir.
SURUM = "1.2.8"                    # optiKA Nöbet Panosu sürümü (pano ile aynı olmalı)
PLAN = ["08:30", "18:00"]          # varsayılan; panodaki Ayarlar > Güncelleme'den değiştirilince plan.json'a yazılır
PLAN_DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan.json")
try:
    with open(PLAN_DOSYA, encoding="utf-8") as _f:
        _p = json.load(_f)
    if isinstance(_p, list) and _p and all(re.fullmatch(r"\d\d:\d\d", x) for x in _p):
        PLAN = _p
except (OSError, ValueError):
    pass
SABAH_SON = "12:00"      # bu saate kadar "bugünün listesi gelmedi" diye tekrar dene
ILERLEME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ilerleme.js")
_ILERLEME_ACIK = False
_ILERLEME_NO = None
DENEME_SAYISI, ZAMAN_ASIMI = 3, 20
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guncelle.log")

# ---- Gerekli paketler: eksikse bu Python'a kendisi kurar (pythonw ile sessiz çalışırken de) ----
def _paketleri_kur():
    import subprocess
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW: konsol penceresi açma
    for ek in ([], ["--user"]):
        try:
            r = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "-m", "pip", "install", "-q",
                                "--disable-pip-version-check", *ek, "requests", "beautifulsoup4", "segno"],
                               capture_output=True, timeout=300, **kw)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    return False

try:
    from bs4 import BeautifulSoup
    import requests  # noqa: F401  (yalnızca varlık kontrolü)
except ImportError:
    if "--ilerleme" in sys.argv:          # panonun giriş ekranı beklerken ne olduğunu görsün
        try:
            with open(ILERLEME, "w", encoding="utf-8") as _f:
                _f.write('window.NOBET_ILERLEME = ' + json.dumps({"basla": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                         "yuzde": 3, "adim": "Eksik Python paketleri kuruluyor (ilk seferde 1-2 dakika)", "bitti": False}, ensure_ascii=False) + ';\n')
        except OSError:
            pass
    _paketleri_kur()
    import importlib, site
    importlib.invalidate_caches()
    try:
        sys.path.append(site.getusersitepackages())
    except Exception:
        pass
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None               # main() bunu yakalar, panoya ve kayda yazar
try:
    import segno
except ImportError:
    segno = None

KOORD_RE = re.compile(r"q=\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")


def ilerle(yuzde, adim, bitti=False, ok=None, **ek):
    """Başlatıcı (--ilerleme) çalıştırdığında panonun giriş ekranındaki % çubuğunu besler."""
    global _ILERLEME_NO
    if not _ILERLEME_ACIK:
        return
    if _ILERLEME_NO is None:
        _ILERLEME_NO = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    veri = {"basla": _ILERLEME_NO, "yuzde": int(yuzde), "adim": adim, "bitti": bitti, "ok": ok, **ek}
    try:
        gecici = ILERLEME + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            f.write("window.NOBET_ILERLEME = " + json.dumps(veri, ensure_ascii=False) + ";\n")
        os.replace(gecici, ILERLEME)
    except OSError:
        pass


def log(msg):
    satir = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(satir)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 1_000_000:   # günlük 1 MB'ı geçerse sıfırla
            os.replace(LOG, LOG + ".eski")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(satir + "\n")
    except OSError:
        pass


def makine_kodu():
    """Bu bilgisayara özgü kısa kod (Windows MachineGuid'den türetilir). Lisans bu koda bağlanabilir."""
    import hashlib, platform
    ham = ""
    try:
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                ham = winreg.QueryValueEx(k, "MachineGuid")[0]
        elif sys.platform == "darwin":
            import subprocess
            cikti = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                   capture_output=True, text=True, timeout=10).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', cikti)
            ham = m.group(1) if m else ""
        else:
            for yol in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(yol):
                    ham = open(yol).read().strip(); break
    except Exception:
        pass
    ham = ham or platform.node()
    h = hashlib.sha256(("optiKA|" + ham).encode()).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}"


def sayfa_getir():
    import requests
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 NobetPanosu/1.1",
         "Cache-Control": "no-cache", "Pragma": "no-cache"}
    son_hata = None
    for deneme in range(DENEME_SAYISI):
        try:
            r = requests.get(KAYNAK, headers=h, params={"_": int(time.time())}, timeout=ZAMAN_ASIMI)  # önbellekteki eski sayfa gelmesin
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            son_hata = e
            if deneme + 1 < DENEME_SAYISI:
                ilerle(15 + 8 * (deneme + 1), f"Bağlantı kurulamadı, yeniden deneniyor ({deneme + 2}/{DENEME_SAYISI})")
                time.sleep(3)
    raise RuntimeError(f"Site okunamadı: {son_hata}")


def tr_buyuk(s):
    return (s or "").replace("i", "İ").replace("ı", "I").upper()


def temiz(s):
    return re.sub(r"\s+", " ", s or "").strip()


def yol_tarifi_url(lat, lng):
    # Telefonda Google Haritalar'ı açar, bulunulan konumdan eczaneye rota çizer
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}&travelmode=driving"


def qr_svg(url):
    if not segno:
        return ""
    q = segno.make(url, error="m")
    return q.svg_inline(scale=1, border=2, dark="#000", light="#fff", omitsize=True)


def kartlardan(soup):
    """Oda sitesinin kendi yapısı: <article class="nobet-card"> (2026-11 itibarıyla)"""
    sonuc = []
    kartlar = soup.select("article.nobet-card")
    for i, kart in enumerate(kartlar):
        if i % 4 == 0:
            ilerle(60 + 35 * i / max(1, len(kartlar)), f"Eczaneler ve QR kodları hazırlanıyor ({i + 1}/{len(kartlar)})")
        harita = kart.select_one('a[href*="maps"]')
        m = KOORD_RE.search(unquote(harita["href"])) if harita else None
        if not m:
            continue
        ad = kart.select_one(".nobet-card-name")
        ilce = kart.select_one(".nobet-card-ilce")
        tel = kart.select_one('a[href^="tel:"]')
        adres = ""
        for p in kart.select("p.nobet-card-line"):
            if p.find("a"):
                continue
            adres = temiz(p.get_text(" "))
            break
        bolum = kart.find_parent("section")
        il_baslik = bolum.find(["h2", "h3"]) if bolum else None
        il = tr_buyuk(temiz(il_baslik.get_text()).split()[0]) if il_baslik else ""
        lat, lng = m.group(1), m.group(2)
        url = yol_tarifi_url(lat, lng)
        sonuc.append({
            "ad": tr_buyuk(temiz(ad.get_text())) if ad else "",
            "ilce": tr_buyuk(temiz(ilce.get_text())) if ilce else "",
            "il": il, "adres": adres,
            "telefon": temiz(tel.get_text()) if tel else "",
            "lat": float(lat), "lng": float(lng), "url": url, "qr": qr_svg(url),
        })
    return sonuc


def ayristir(html):
    soup = BeautifulSoup(html, "html.parser")
    guncelleme = ""
    gm = re.search(r"Son güncelleme:\s*([^\n<]+)", soup.get_text("\n"))
    if gm:
        guncelleme = temiz(gm.group(1))

    eczaneler = kartlardan(soup)
    if eczaneler:
        return eczaneler, guncelleme
    # Site tasarımı değişirse: genel yöntem (harita linklerinden geriye doğru)
    eczaneler, gorulen = [], set()

    for a in soup.find_all("a", href=True):
        href = unquote(a["href"])
        if "google." not in href or "maps" not in href:
            continue
        m = KOORD_RE.search(href)
        if not m:
            continue
        lat, lng = m.group(1), m.group(2)

        # Bu linki içeren ve yalnızca TEK harita linki barındıran en geniş kutuyu bul
        kutu = a
        while kutu.parent is not None:
            ust = kutu.parent
            linkler = [x for x in ust.find_all("a", href=True) if KOORD_RE.search(unquote(x["href"]))]
            if len(linkler) > 1:
                break
            kutu = ust

        baslik = kutu.find(["h1", "h2", "h3", "h4", "h5", "strong", "b"])
        ad_ham = temiz(baslik.get_text(" ")) if baslik else ""
        if not ad_ham:
            # başlık etiketi yoksa ilk anlamlı satır
            satirlar = [temiz(s) for s in kutu.get_text("\n").split("\n") if temiz(s)]
            ad_ham = next((s for s in satirlar if "ECZANE" in s.upper()), satirlar[0] if satirlar else "")

        tel_a = kutu.find("a", href=re.compile(r"^tel:", re.I))
        telefon = temiz(tel_a.get_text()) if tel_a else ""
        if not telefon:
            tm = re.search(r"0\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}", kutu.get_text(" "))
            telefon = temiz(tm.group(0)) if tm else ""

        # Adres: kutudaki metinden ad, telefon ve link yazısı çıkarılınca kalan
        haric = {ad_ham, telefon, temiz(a.get_text())}
        satirlar = [temiz(s) for s in kutu.get_text("\n").split("\n")]
        adres_parca = [s for s in satirlar if s and s not in haric
                       and "haritada" not in s.lower() and "tıklayınız" not in s.lower()
                       and not re.fullmatch(r"[\d\s()+-]{7,}", s)]
        adres = temiz(" ".join(adres_parca))

        # "ALBAYRAK ECZANESİ - İLKADIM" -> ad + ilçe
        if " - " in ad_ham:
            ad, ilce = ad_ham.rsplit(" - ", 1)
        else:
            ad, ilce = ad_ham, ""
        ad, ilce = tr_buyuk(temiz(ad)), tr_buyuk(temiz(ilce))

        # İl: önceki "... Bugün Nöbetçi Eczaneler" başlığından
        il = ""
        onceki = a.find_previous(string=re.compile(r"Bugün\s+Nöbetçi", re.I))
        if onceki:
            il = tr_buyuk(temiz(onceki).split()[0])

        anahtar = (ad, lat, lng)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)

        url = yol_tarifi_url(lat, lng)
        eczaneler.append({
            "ad": ad, "ilce": ilce, "il": il, "adres": adres, "telefon": telefon,
            "lat": float(lat), "lng": float(lng), "url": url, "qr": qr_svg(url),
        })

    guncelleme = ""
    gm = re.search(r"Son güncelleme:\s*([^\n<]+)", soup.get_text("\n"))
    if gm:
        guncelleme = temiz(gm.group(1))
    return eczaneler, guncelleme


def eski_veri():
    try:
        with open(CIKTI, encoding="utf-8") as f:
            t = f.read()
        return json.loads(t[t.index("{"):t.rindex("}") + 1])
    except Exception:
        return {}


def imza_hesapla(eczaneler):
    import hashlib
    ozet = [(e["il"], e["ilce"], e["ad"], e["adres"], e["telefon"], e["lat"], e["lng"]) for e in eczaneler]
    return hashlib.sha1(json.dumps(sorted(ozet), ensure_ascii=False).encode()).hexdigest()[:12]


def yaz(eczaneler, site_guncelleme, aralik=5):
    eski = eski_veri()
    imza = imza_hesapla(eczaneler)
    degisiklik = eski.get("degisiklik")   # yalnızca liste gerçekten değişince dolar
    if eski.get("imza") and eski.get("imza") != imza:
        degisiklik = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        ad = lambda e: f'{e["ad"]} ({e["ilce"]})'
        onceki = {ad(e) for e in eski.get("eczaneler", [])}
        simdi = {ad(e) for e in eczaneler}
        log(f"DEĞİŞİKLİK  çıkan: {', '.join(sorted(onceki - simdi)) or '-'}  |  giren: {', '.join(sorted(simdi - onceki)) or '-'}")
    simdi = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    veri = {
        "son_deneme": simdi,
        "hata": None,
        "imza": imza,
        "degisiklik": degisiklik,
        "kaynak": KAYNAK,
        "cekilme": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "site_guncelleme": site_guncelleme,
        "qr_var": bool(segno),
        "makine": makine_kodu(),
        "aralik_dk": aralik,
        "plan": PLAN,
        "surum": kurulu_surum(),
        "eczaneler": eczaneler,
    }
    gecici = CIKTI + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        f.write("window.NOBET_VERI = ")
        json.dump(veri, f, ensure_ascii=False, indent=1)
        f.write(";\n")
    os.replace(gecici, CIKTI)  # pano yarım dosya okumasın


def hata_kaydet(mesaj):
    """Başarısız denemeyi panoya bildir: eski liste korunur, yalnızca deneme zamanı ve hata yazılır."""
    try:
        eski = eski_veri()
        if not eski:
            return
        eski["son_deneme"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        kisa = "İnternet/site bağlantısı kurulamadı" if any(k in mesaj for k in ("Site okunamadı", "Connection", "Timeout", "resolve", "SSL")) else mesaj[:120]
        eski["hata"] = kisa
        gecici = CIKTI + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            f.write("window.NOBET_VERI = ")
            json.dump(eski, f, ensure_ascii=False, indent=1)
            f.write(";\n")
        os.replace(gecici, CIKTI)
    except Exception:
        pass


AYLAR = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"]


def site_tarihi(metin):
    """'05 Kasım 2026 Perşembe · 08:30' -> date"""
    m = re.search(r"(\d{1,2})\s+(\S+)\s+(\d{4})", metin or "")
    if not m:
        return None
    ay = m.group(2).replace("I", "ı").replace("İ", "i").lower()
    if ay not in AYLAR:
        return None
    from datetime import date
    return date(int(m.group(3)), AYLAR.index(ay) + 1, int(m.group(1)))


def saat(t, gun):
    h, d = map(int, t.split(":"))
    return gun.replace(hour=h, minute=d, second=0, microsecond=0)


def simdi_gerekli_mi():
    """Zamanlanmış çalışmada siteye gidilmeli mi? (Plan saatleri dışında siteyi yormaz)"""
    from datetime import timedelta
    now = datetime.now()
    eski = eski_veri()
    if not eski.get("cekilme"):
        return True, "ilk veri"
    try:
        son_ok = datetime.fromisoformat(eski["cekilme"])
    except Exception:
        return True, "tarih okunamadı"
    # Son geçen plan saati (bugün ya da dün akşam)
    gecmis = [saat(t, now) for t in PLAN if saat(t, now) <= now]
    son_plan = max(gecmis) if gecmis else saat(PLAN[-1], now - timedelta(days=1))
    if son_ok < son_plan:
        return True, f"{son_plan:%H:%M} planı"
    # Sabah: sitede bugünün listesi yoksa SABAH_SON'a kadar yeniden dene
    if saat(PLAN[0], now) <= now < saat(SABAH_SON, now):
        st = site_tarihi(eski.get("site_guncelleme"))
        if st is None or st < now.date():
            try:
                son_deneme = datetime.fromisoformat(eski.get("son_deneme") or eski["cekilme"])
            except Exception:
                son_deneme = son_ok
            if (now - son_deneme).total_seconds() >= 240:
                return True, "bugünün listesi henüz gelmedi"
    return False, ""


def plan_kaydet(metin):
    """nobetpanosu://plan/08:30,18:00 -> plan.json (+ panonun gösterdiği plan alanı)"""
    saatler = sorted({f"{int(h):02d}:{int(m):02d}" for h, m in re.findall(r"(\d{1,2}):(\d{2})", metin)
                      if int(h) < 24 and int(m) < 60})[:2]
    if not saatler:
        raise RuntimeError("Geçerli saat bulunamadı")
    with open(PLAN_DOSYA, "w", encoding="utf-8") as f:
        json.dump(saatler, f)
    eski = eski_veri()
    if eski:
        eski["plan"] = saatler
        gecici = CIKTI + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            f.write("window.NOBET_VERI = ")
            json.dump(eski, f, ensure_ascii=False, indent=1)
            f.write(";\n")
        os.replace(gecici, CIKTI)
    log(f"Güncelleme saatleri kaydedildi: {', '.join(saatler)}")
    return saatler


YARDIMCI_PORT = 47831          # yalnızca bu bilgisayar (127.0.0.1); panodaki "Şimdi güncelle" / "Saatleri kaydet" buraya bağlanır


# Panonun kurulu olduğu klasörler (yardımcı yalnızca bunlarda güncelleme çalıştırır; başka klasörü kabul etmez)
KLASOR_KAYIT = os.path.join(os.path.expanduser("~"), ".optika_nobet_panosu_klasorler.json")
BU_KLASOR = os.path.dirname(os.path.abspath(__file__))


def _norm(yol):
    return os.path.normcase(os.path.realpath(yol))


def klasor_kaydet():
    try:
        try:
            with open(KLASOR_KAYIT, encoding="utf-8") as f:
                liste = json.load(f)
        except (OSError, ValueError):
            liste = []
        if _norm(BU_KLASOR) not in [_norm(x) for x in liste]:
            liste = ([x for x in liste if os.path.exists(os.path.join(x, "guncelle.py"))] + [BU_KLASOR])[-20:]
            with open(KLASOR_KAYIT, "w", encoding="utf-8") as f:
                json.dump(liste, f, ensure_ascii=False)
    except Exception:
        pass


def kayitli_klasor(yol):
    """Panodan gelen klasör kayıtlıysa ve içinde pano dosyaları varsa onu döndürür."""
    if not yol:
        return None
    try:
        with open(KLASOR_KAYIT, encoding="utf-8") as f:
            liste = json.load(f)
    except (OSError, ValueError):
        return None
    hedef = _norm(yol)
    for x in liste:
        if _norm(x) == hedef and os.path.isfile(os.path.join(x, "guncelle.py")) and os.path.isfile(os.path.join(x, "nobet_panosu.html")):
            return x
    return None


# ---- Lisans kodu: optiKA'nın imzası saf Python ile doğrulanır (ECDSA P-256 / SHA-256), sonra lisans.js yazılır ----
OPTIKA_ACIK_ANAHTAR = "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAENjXiEASiWzQAkDd9o0anLySNJaMB/FtXmWRhAxE+OJI/2ICrkEGgQrNXfkcjjIhScYzNvzzAuUgIOzYlmlzYlg=="
_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
_N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
_A = _P - 3
_G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
      0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)


def _ekle(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        m = (3 * a[0] * a[0] + _A) * pow(2 * a[1], -1, _P) % _P
    else:
        m = (b[1] - a[1]) * pow(b[0] - a[0], -1, _P) % _P
    x = (m * m - a[0] - b[0]) % _P
    return (x, (m * (a[0] - x) - a[1]) % _P)


def _carp(k, nokta):
    sonuc = None
    while k:
        if k & 1:
            sonuc = _ekle(sonuc, nokta)
        nokta = _ekle(nokta, nokta)
        k >>= 1
    return sonuc


def imza_dogru(veri_metni, imza_b64):
    import base64, hashlib
    try:
        acik = base64.b64decode(OPTIKA_ACIK_ANAHTAR)[-65:]
        Q = (int.from_bytes(acik[1:33], "big"), int.from_bytes(acik[33:], "big"))
        imza = base64.b64decode(imza_b64)
        if len(imza) != 64:
            return False
        r, s_ = int.from_bytes(imza[:32], "big"), int.from_bytes(imza[32:], "big")
        if not (0 < r < _N and 0 < s_ < _N):
            return False
        e = int.from_bytes(hashlib.sha256(veri_metni.encode("utf-8")).digest(), "big")
        w = pow(s_, -1, _N)
        X = _ekle(_carp(e * w % _N, _G), _carp(r * w % _N, Q))
        return X is not None and X[0] % _N == r
    except Exception:
        return False


def lisans_kodu_coz(kod):
    """'OPTIKA1.<base64>' -> {'veri':..., 'imza':...} (imza doğrulanmış)"""
    import base64
    kod = re.sub(r"\s+", "", kod or "")
    if kod.upper().startswith("OPTIKA1."):
        kod = kod[8:]
    kod += "=" * (-len(kod) % 4)
    L = json.loads(base64.urlsafe_b64decode(kod).decode("utf-8"))
    if not isinstance(L, dict) or not isinstance(L.get("veri"), str) or not isinstance(L.get("imza"), str):
        raise ValueError("Lisans kodu bozuk")
    if not imza_dogru(L["veri"], L["imza"]):
        raise ValueError("Lisans kodu geçersiz (optiKA imzası tutmuyor)")
    return {"veri": L["veri"], "imza": L["imza"]}


def lisans_yaz(klasor, L):
    hedef = os.path.join(klasor, "lisans.js")
    if os.path.exists(hedef):
        try:
            import shutil
            shutil.copyfile(hedef, os.path.join(klasor, "lisans_onceki.js"))
        except OSError:
            pass
    gecici = hedef + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        f.write("// optiKA lisans dosyası - DEĞİŞTİRMEYİN (imza bozulur)\nwindow.OPTIKA_LISANS = ")
        json.dump(L, f, ensure_ascii=False)
        f.write(";\n")
    os.replace(gecici, hedef)
    v = json.loads(L["veri"])
    log(f"Lisans kodu yüklendi: {v.get('eczane')} · bitiş {v.get('bitis')} · no {v.get('lisans_no')}")
    return v


# ======================= Uygulama güncellemesi (Cloudflare) =======================
# optiKA yeni sürümü Cloudflare'e yükler; eczanedeki sistem surum.json'u okur, optiKA imzasını
# doğrular, dosyaları indirip SHA-256 ile kontrol eder ve yalnızca uygulama dosyalarını değiştirir.
# lisans.js, nobet_veri.js, plan.json ve panodaki ayarlar ASLA değiştirilmez.
GUNCELLEME_ADRESLERI = ["https://young-cake-c775.aykut-yazicioglu.workers.dev", "https://optika-nobet.aykut-yazicioglu.workers.dev"]
ADRES_DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guncelleme_adresi.txt")
UYG_DURUM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uygulama_guncelleme.json")
_YASAK = {"lisans.js", "lisans_onceki.js", "nobet_veri.js", "plan.json", "ilerleme.js",
          "guncelleme_adresi.txt", "uygulama_guncelleme.json", "uygulama_guncelleme.js", "guncelle.log"}


def guncelleme_adresleri():
    adresler = []
    try:
        with open(ADRES_DOSYA, encoding="utf-8") as f:
            adresler = [x.strip().rstrip("/") for x in f if x.strip().startswith("https://")]
    except OSError:
        pass
    for a in GUNCELLEME_ADRESLERI:
        if a not in adresler:
            adresler.append(a)
    return adresler


def kurulu_surum(klasor=None):
    """Diskteki guncelle.py'nin sürümü (çalışan süreç eski kalmış olsa bile kurulu olanı verir)."""
    try:
        with open(os.path.join(klasor or os.path.dirname(os.path.abspath(__file__)), "guncelle.py"), encoding="utf-8") as f:
            m = re.search(r'^SURUM = "([\d.]+)"', f.read(), re.M)
        return m.group(1) if m else SURUM
    except OSError:
        return SURUM


def surum_sayi(s):
    try:
        return tuple(int(x) for x in str(s).strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


def _guvenli_ad(ad):
    if not isinstance(ad, str) or not re.fullmatch(r"[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)?", ad):
        return False
    if ".." in ad or ad.startswith("/") or os.path.basename(ad) in _YASAK:
        return False
    return "/" not in ad or ad.split("/")[0] == "simge"


def _uyg_durum_yaz(klasor=None, **veri):
    veri["zaman"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    hedef = os.path.join(klasor, "uygulama_guncelleme.json") if klasor else UYG_DURUM
    try:
        with open(hedef + ".tmp", "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
        os.replace(hedef + ".tmp", hedef)
        js = hedef[:-5] + ".js"                # pano (file://) yalnızca .js okuyabilir
        with open(js + ".tmp", "w", encoding="utf-8") as f:
            f.write("window.UYG_GUNCELLEME = " + json.dumps(veri, ensure_ascii=False) + ";\n")
        os.replace(js + ".tmp", js)
    except OSError:
        pass


def uygulama_guncelle(klasor=None, zorla=False, adimli=False):
    """Yeni sürüm varsa kurar. Dönüş: {'ok', 'yeni', 'surum', 'mesaj'}
    adimli=True: panodaki % çubuğunu adım adım besler (Uygulamayı güncelle düğmesi)."""
    import requests, hashlib, shutil
    klasor = klasor or os.path.dirname(os.path.abspath(__file__))
    mevcut = kurulu_surum(klasor)
    if adimli == "liste":       # liste güncellemesinin içinde: çubuğun %88–99 aralığını kullan, bitirme
        adim = lambda y, m: ilerle(88 + y * 11 // 100, m)
    elif adimli:
        adim = lambda y, m: ilerle(y, m, uygulama=True)
    else:
        adim = lambda y, m: None

    def bitir(sonuc):
        if adimli is True:
            ilerle(100, sonuc["mesaj"], bitti=True, ok=sonuc["ok"], uygulama=True,
                   yeni=sonuc.get("yeni"), surum=sonuc.get("surum"))
        return sonuc
    son_hata = "Güncelleme sunucusuna ulaşılamadı"
    for adres in guncelleme_adresleri():
        try:
            adim(10, "Güncelleme sunucusuna bağlanılıyor")
            r = requests.get(adres + "/surum.json", params={"_": int(time.time())}, timeout=15,
                             headers={"Cache-Control": "no-cache", "User-Agent": "optiKA-NobetPanosu/" + SURUM})
            r.raise_for_status()
            M = r.json()
            adim(20, "optiKA imzası doğrulanıyor")
            if not imza_dogru(M.get("veri", ""), M.get("imza", "")):
                son_hata = "Güncelleme paketi optiKA imzası taşımıyor — kurulmadı"
                log("UYGULAMA GÜNCELLEME  imza tutmadı: " + adres)
                continue
            V = json.loads(M["veri"])
            yeni = str(V.get("surum", ""))
            if V.get("urun") != "optiKA Nöbet Panosu":
                son_hata = "Paket bu ürüne ait değil"; continue
            # imzalı yeni adres listesi (ileride sunucu değişirse)
            if isinstance(V.get("adresler"), list) and V["adresler"]:
                try:
                    with open(ADRES_DOSYA, "w", encoding="utf-8") as f:
                        f.write("\n".join(a for a in V["adresler"] if str(a).startswith("https://")) + "\n")
                except OSError:
                    pass
            if not zorla and surum_sayi(yeni) <= surum_sayi(mevcut):
                _uyg_durum_yaz(klasor, ok=True, yeni=False, surum=mevcut, sunucu=yeni)
                return bitir({"ok": True, "yeni": False, "surum": mevcut, "mesaj": f"Uygulama güncel (v{mevcut})"})
            dosyalar = V.get("dosyalar") or []
            if not dosyalar or not all(_guvenli_ad(d.get("ad")) for d in dosyalar):
                son_hata = "Paket dosya listesi geçersiz"; continue
            # 1) Hepsini indir ve doğrula (hiçbir dosyaya dokunmadan)
            indirilen = {}
            for i, d in enumerate(dosyalar):
                adim(30 + 60 * i // len(dosyalar), f"v{yeni} indiriliyor ({i + 1}/{len(dosyalar)}) · {d['ad']}")
                g = requests.get(adres + "/dosyalar/" + d["ad"], params={"v": yeni}, timeout=30)
                g.raise_for_status()
                if hashlib.sha256(g.content).hexdigest() != d.get("sha256"):
                    raise RuntimeError(f"{d['ad']} bozuk indi (SHA-256 tutmuyor)")
                indirilen[d["ad"]] = g.content
            # 2) Eski dosyaları yedekle, sonra yenileri yerine koy
            adim(95, f"v{yeni} kuruluyor")
            yedek = os.path.join(klasor, ".yedek", "v" + mevcut)
            for ad, icerik in indirilen.items():
                hedef = os.path.join(klasor, *ad.split("/"))
                os.makedirs(os.path.dirname(hedef), exist_ok=True)
                if os.path.exists(hedef):
                    os.makedirs(os.path.dirname(os.path.join(yedek, *ad.split("/"))), exist_ok=True)
                    shutil.copy2(hedef, os.path.join(yedek, *ad.split("/")))
                with open(hedef + ".yeni", "wb") as f:
                    f.write(icerik)
            for ad in indirilen:
                hedef = os.path.join(klasor, *ad.split("/"))
                os.replace(hedef + ".yeni", hedef)
            if V.get("kurulum_yenile"):
                # Başlatıcı bir sonraki açılışta kurulumu yeniden yapsın (masaüstü simgesi, Mac uygulaması vb.)
                import glob
                for iz in glob.glob(os.path.join(klasor, ".kurulum", "surum_*.txt")) + glob.glob(os.path.join(klasor, ".kurulum_surum_*")):
                    try:
                        os.remove(iz)
                    except OSError:
                        pass
            log(f"UYGULAMA GÜNCELLENDİ  v{mevcut} → v{yeni}  ({len(indirilen)} dosya, kaynak {adres})")
            _uyg_durum_yaz(klasor, ok=True, yeni=True, surum=yeni, onceki=mevcut, notlar=V.get("notlar", []))
            return bitir({"ok": True, "yeni": True, "surum": yeni, "mesaj": f"v{yeni} kuruldu", "notlar": V.get("notlar", [])})
        except Exception as e:
            son_hata = f"{son_hata if 'imza' in son_hata else 'Güncelleme alınamadı'}: {e}"[:200]
            log("UYGULAMA GÜNCELLEME  " + adres + "  " + str(e))
            continue
    _uyg_durum_yaz(klasor, ok=False, yeni=False, surum=mevcut, hata=son_hata)
    return bitir({"ok": False, "yeni": False, "surum": mevcut, "mesaj": son_hata})


def yardimci_calisiyor():
    import socket
    try:
        with socket.create_connection(("127.0.0.1", YARDIMCI_PORT), timeout=1):
            return True
    except OSError:
        return False


def _arka_planda(*argumanlar, klasor=None):
    """Bu betiği (ya da kayıtlı başka klasördeki kopyasını) ayrı, pencere açmayan bir süreç olarak başlat."""
    betik = os.path.join(klasor, "guncelle.py") if klasor else os.path.abspath(__file__)
    import subprocess
    py = sys.executable
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        pyw = py.replace("python.exe", "pythonw.exe")
        py = pyw if os.path.exists(pyw) else py
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x01000000 | 0x08000000
    else:
        kw["start_new_session"] = True
    try:
        return subprocess.Popen([py, betik, *argumanlar], cwd=os.path.dirname(betik), **kw)
    except OSError:
        if os.name == "nt":                       # iş nesnesinden ayrılmaya izin yoksa bayraksız dene
            kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
            return subprocess.Popen([py, betik, *argumanlar], cwd=os.path.dirname(betik), **kw)
        raise


def bosta_saniye():
    """Bilgisayara en son dokunulmasından (fare/klavye) bu yana geçen saniye; bilinmiyorsa None."""
    try:
        if os.name == "nt":
            import ctypes
            class LII(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            l = LII(); l.cbSize = ctypes.sizeof(LII)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(l)):
                return None
            return ((ctypes.windll.kernel32.GetTickCount() - l.dwTime) & 0xFFFFFFFF) / 1000.0
        if sys.platform == "darwin":
            import subprocess
            c = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', c)
            return int(m.group(1)) / 1e9 if m else None
    except Exception:
        return None
    return None


def tam_ekrana_dondur(tarayici="chrome"):
    """Pano penceresini öne alıp F13 gönderir: pano kayıtlı tercihe göre tam ekrana geçer (başlatıcıdaki yöntemin aynısı)."""
    import subprocess
    if os.name == "nt":
        komut = ("$w=New-Object -ComObject WScript.Shell; if($w.AppActivate('Eczaneler')){ Start-Sleep -Milliseconds 400; "
                 "$w.SendKeys('{F13}'); 'ok' } else { 'yok' }")
        r = subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", komut],
                           capture_output=True, text=True, timeout=20, creationflags=0x08000000)
        return "ok" in (r.stdout or "")
    if sys.platform == "darwin":
        uyg = "Microsoft Edge" if tarayici == "edge" else "Google Chrome"
        betik = f'''
tell application "System Events"
  set bulundu to false
  repeat with p in (every process whose name is "{uyg}")
    repeat with w in (every window of p)
      if name of w contains "Eczaneler" then
        set frontmost of p to true
        perform action "AXRaise" of w
        set bulundu to true
        exit repeat
      end if
    end repeat
    if bulundu then exit repeat
  end repeat
  if bulundu then
    delay 0.4
    key code 105
    return "ok"
  end if
  return "yok"
end tell'''
        r = subprocess.run(["osascript", "-e", betik], capture_output=True, text=True, timeout=20)
        return "ok" in (r.stdout or "")
    return False


def yardimci_sunucu():
    """Panonun düğmeleri için küçük yerel sunucu. Yalnızca 127.0.0.1'i dinler, dışarıdan erişilemez."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs
    import threading
    durum = {"surec": None}
    kilit = threading.Lock()

    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _yanit(self, kod, veri):
            govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.end_headers()

        def do_POST(self):
            u = urlparse(self.path)
            if u.path != "/lisans":
                return self._yanit(404, {"ok": False})
            try:
                uzunluk = min(int(self.headers.get("Content-Length") or 0), 20000)
                govde = json.loads(self.rfile.read(uzunluk).decode("utf-8"))
                L = lisans_kodu_coz(govde.get("kod", ""))
                klasor = kayitli_klasor(govde.get("klasor")) or BU_KLASOR
                v = lisans_yaz(klasor, L)
                return self._yanit(200, {"ok": True, "eczane": v.get("eczane"), "bitis": v.get("bitis")})
            except Exception as e:
                return self._yanit(400, {"ok": False, "hata": str(e)})

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            istenen = q.get("klasor", [""])[0]
            hedef = kayitli_klasor(istenen)          # panonun kendi klasörü (kayıtlıysa)
            if u.path == "/durum":
                return self._yanit(200, {"ok": True, "plan": PLAN, "klasor": BU_KLASOR,
                                         "panoKlasoruTanindi": bool(hedef) or (bool(istenen) and _norm(istenen) == _norm(BU_KLASOR))})
            if u.path == "/guncelle":
                with kilit:
                    s = durum["surec"]
                    if s is not None and s.poll() is None:
                        return self._yanit(200, {"ok": True, "zaten": True})
                    durum["surec"] = _arka_planda("--ilerleme", klasor=hedef)
                return self._yanit(200, {"ok": True, "klasor": hedef or BU_KLASOR})
            if u.path == "/uygulama":
                # Panodaki "Uygulamayı güncelle" düğmesi: panonun klasöründe ayrı süreç olarak çalışır,
                # ilerlemeyi ilerleme.js'e yazar (pano % çubuğunu gösterir)
                with kilit:
                    s_ = durum.get("uyg")
                    if s_ is not None and s_.poll() is None:
                        return self._yanit(200, {"ok": True, "basladi": True, "zaten": True})
                    ek = ["--uygulama", "--ilerleme"] + (["--zorla"] if q.get("zorla", [""])[0] == "1" else [])
                    durum["uyg"] = _arka_planda(*ek, klasor=hedef)
                return self._yanit(200, {"ok": True, "basladi": True})
            if u.path == "/tamekran":
                # Tam ekran koruması: pano pencereye düştüyse ve bilgisayar bir süredir boştaysa geri al
                try:
                    gerekli = max(10, min(3600, int(q.get("bos", ["90"])[0])))
                except ValueError:
                    gerekli = 90
                bos = bosta_saniye()
                simdi = time.time()
                if bos is not None and bos < gerekli:
                    return self._yanit(200, {"ok": True, "gonderildi": False, "bosta": round(bos), "bekle": gerekli})
                if simdi - durum.get("tamSon", 0) < 45:       # art arda denemeyi sınırla
                    return self._yanit(200, {"ok": True, "gonderildi": False, "sinir": True})
                durum["tamSon"] = simdi
                try:
                    ok = tam_ekrana_dondur(q.get("t", ["chrome"])[0])
                except Exception as e:
                    ok = False
                    log(f"Tam ekran koruması: {e}")
                log("Tam ekran koruması: pano tam ekrana alındı" if ok else "Tam ekran koruması: pano penceresi bulunamadı/izin yok")
                return self._yanit(200, {"ok": True, "gonderildi": ok})
            if u.path == "/plan":
                saatler = q.get("s", [""])[0]
                try:
                    if hedef and _norm(hedef) != _norm(BU_KLASOR):   # panonun klasöründeki kopyaya kaydettir
                        r = _arka_planda("--ilerleme", "nobetpanosu://plan/" + saatler, klasor=hedef)
                        r.wait(timeout=30)
                        return self._yanit(200, {"ok": r.returncode == 0, "plan": sorted(set(re.findall(r"\d\d:\d\d", saatler)))[:2]})
                    kayit = plan_kaydet(saatler)
                    PLAN[:] = kayit
                    return self._yanit(200, {"ok": True, "plan": kayit})
                except Exception as e:
                    return self._yanit(400, {"ok": False, "hata": str(e)})
            return self._yanit(404, {"ok": False})

    try:
        sunucu = ThreadingHTTPServer(("127.0.0.1", YARDIMCI_PORT), Isleyici)
    except OSError:
        return                                   # zaten çalışıyor
    log(f"Yardımcı program başladı (127.0.0.1:{YARDIMCI_PORT}) v{SURUM}")

    # Program güncellenince (guncelle.py değişince) yardımcı kendini yeni sürümle yeniden başlatır:
    # yoksa eski kod bellekte çalışmaya devam eder ve yeni özellikler (ör. tam ekran koruması) devreye girmez.
    def _degisiklik_izle():
        try:
            ilk = os.path.getmtime(os.path.abspath(__file__))
        except OSError:
            return
        while True:
            time.sleep(30)
            try:
                if os.path.getmtime(os.path.abspath(__file__)) != ilk:
                    time.sleep(5)                     # dosya yazımı bitsin
                    log("Yardımcı program: yeni sürüm algılandı, yeniden başlatılıyor")
                    sunucu.shutdown()
                    return
            except OSError:
                pass
    threading.Thread(target=_degisiklik_izle, daemon=True).start()
    sunucu.serve_forever()
    sunucu.server_close()
    if durum.get("yeniden") is not False:
        try:
            _arka_planda("--yardimci")
        except Exception as e:
            log(f"Yardımcı yeniden başlatılamadı: {e}")


def _uygulama_da(arg):
    """Liste güncellemesiyle birlikte (zamanlı / açılış / Şimdi güncelle) program güncellemesine de bak."""
    if not (arg.zamanli or arg.ilerleme) or arg.html:
        return None
    try:
        ilerle(88, "Program güncellemesi kontrol ediliyor")
        u = uygulama_guncelle(adimli="liste")
        if u.get("yeni"):
            log(f"Otomatik uygulama güncellemesi: v{u['surum']}")
        return u
    except Exception as e:
        log(f"Uygulama güncelleme kontrolü atlandı: {e}")
        return None


def _kurulumu_yenile_isaretle(klasor=None):
    import glob
    klasor = klasor or os.path.dirname(os.path.abspath(__file__))
    for iz in glob.glob(os.path.join(klasor, ".kurulum", "surum_*.txt")) + glob.glob(os.path.join(klasor, ".kurulum_surum_*")):
        try:
            os.remove(iz)
        except OSError:
            pass


def _simge_gecisi():
    """v1.2.0 yeni optiKA simgesi: eski sürümden Cloudflare ile gelindiyse bir kez kurulumu yeniletir
    (masaüstü kısayolu / Mac uygulaması yeni simgeyle yeniden oluşsun). Yeni kurulumlarda çalışmaz."""
    klasor = os.path.dirname(os.path.abspath(__file__))
    isaret = os.path.join(klasor, ".simge_v120")
    if os.path.exists(isaret):
        return
    try:
        with open(UYG_DURUM, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("onceki") and surum_sayi(d["onceki"]) < (1, 2, 0):
            _kurulumu_yenile_isaretle(klasor)
            log("Yeni simge için kurulum bir sonraki açılışta yenilenecek")
    except (OSError, ValueError):
        pass
    try:
        with open(isaret, "w") as f:
            f.write("1")
    except OSError:
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--html", help="Siteden çekmek yerine kayıtlı HTML dosyasını kullan")
    p.add_argument("--kod", action="store_true", help="Bu bilgisayarın lisans kodunu göster")
    p.add_argument("--aralik", type=int, default=5, help="Zamanlanmış görevin kaç dakikada bir çalıştığı (panodaki uyarı süresi için)")
    p.add_argument("adres", nargs="?", help="Panodan gelen nobetpanosu://guncelle ya da nobetpanosu://plan/08:30,18:00")
    p.add_argument("--yardimci", action="store_true", help="Panonun düğmeleri için yerel yardımcı programı çalıştır")
    p.add_argument("--ilerleme", action="store_true", help="Başlatıcıdan: panonun giriş ekranına yüzde ilerleme bildir")
    p.add_argument("--zamanli", action="store_true", help="Zamanlanmış görev: siteye yalnızca plan saatlerinde (08:30, 18:00) git")
    p.add_argument("--uygulama", action="store_true", help="Uygulama güncellemesini kontrol et ve varsa kur")
    p.add_argument("--zorla", action="store_true", help="--uygulama ile: sürüm aynı olsa da yeniden kur")
    arg = p.parse_args()
    global _ILERLEME_ACIK, DENEME_SAYISI, ZAMAN_ASIMI, _ILERLEME_NO
    if arg.ilerleme and arg.uygulama:
        _ILERLEME_ACIK = True
        _ILERLEME_NO = None
        ilerle(5, "Uygulama güncellemesi başlatılıyor", uygulama=True)
    elif arg.ilerleme:
        _ILERLEME_ACIK = True
        _ILERLEME_NO = None
        DENEME_SAYISI, ZAMAN_ASIMI = 2, 10     # açılışı uzun bekletme
        ilerle(5, "Başlatılıyor")
        log("Açılış güncellemesi başladı (başlatıcı)")
    klasor_kaydet()
    _simge_gecisi()
    if arg.uygulama:
        sonuc = uygulama_guncelle(zorla=arg.zorla, adimli=arg.ilerleme)
        print(sonuc["mesaj"])
        return
    if arg.yardimci:
        yardimci_sunucu()
        return
    # Zamanlanmış görev (Windows): yardımcı program kapanmışsa yeniden başlat
    if arg.zamanli and os.name == "nt" and not yardimci_calisiyor():
        try:
            _arka_planda("--yardimci")
        except Exception as e:
            log(f"Yardımcı program başlatılamadı: {e}")
    if BeautifulSoup is None and not arg.kod:
        msg = "Python paketleri kurulamadı (internet?) — NOBET_PANOSU dosyasını 'kur' ile yeniden çalıştırın"
        log("HATA  " + msg + f"  [{sys.executable}]")
        ilerle(100, msg, bitti=True, ok=False)
        return
    if arg.adres and "plan" in unquote(arg.adres).lower():
        try:
            saatler = plan_kaydet(unquote(arg.adres).split("plan", 1)[1])
            ilerle(100, "Güncelleme saatleri kaydedildi: " + " ve ".join(saatler), bitti=True, ok=True)
        except Exception as e:
            ilerle(100, f"Saatler kaydedilemedi: {e}", bitti=True, ok=False)
        return
    if arg.zamanli and not arg.html and not arg.kod:
        gerek, neden = simdi_gerekli_mi()
        if not gerek:
            return          # plan saati değil: siteye hiç bağlanma
        log(f"Planlı kontrol ({neden})")
    if arg.kod:
        print("Bilgisayar kodu:", makine_kodu())
        return
    try:
        if arg.html:
            with open(arg.html, encoding="utf-8") as f:
                html = f.read()
        else:
            ilerle(15, "Eczacı odası sitesine bağlanılıyor")
            html = sayfa_getir()
        ilerle(50, "Nöbet listesi indirildi, okunuyor")
        eczaneler, gun = ayristir(html)
        if not eczaneler:
            # Eski veriyi silme; pano eski veriyi "güncel değil" uyarısıyla gösterir
            raise RuntimeError("Sayfada eczane bulunamadı (site yapısı değişmiş olabilir)")
        ilerle(85, "Liste kaydediliyor")
        yaz(eczaneler, gun, arg.aralik)
        u = _uygulama_da(arg) or {}
        ilerle(100, ("Güncel liste alındı · " + u["mesaj"]) if u.get("yeni") else "Güncel liste alındı",
               bitti=True, ok=True, site=gun, adet=len(eczaneler), uygulama_yeni=bool(u.get("yeni")), uygulama_surum=u.get("surum"))
        ilceler = sorted({e["ilce"] for e in eczaneler})
        log(f"OK  {len(eczaneler)} eczane, {len(ilceler)} ilçe. Site: {gun or '-'}"
            + ("" if segno else "  (UYARI: segno yok, QR üretilmedi)"))
        print(f"\n  >> Liste kaydedildi: {CIKTI}\n  >> Panoda en geç 1 dakika içinde görünür."
              f"\n  >> Pano bu klasördeki nobet_panosu.html olmalı (başka klasördeki kopya güncellenmez).")
        if gun and datetime.now().strftime("%d") != gun[:2].zfill(2) and datetime.now().hour * 60 + datetime.now().minute >= 9 * 60 + 15:
            print("  !! DİKKAT: Odanın sitesindeki liste bugünün tarihini taşımıyor: " + gun)
    except Exception as e:
        log(f"HATA  {e}")
        _uygulama_da(arg)                    # oda sitesi açılmasa da program güncellemesi denensin
        kisa = "İnternet/site bağlantısı kurulamadı" if "Site okunamadı" in str(e) else str(e)[:120]
        ilerle(100, kisa, bitti=True, ok=False)
        print("\n  !! Liste ALINAMADI. Bu pencerenin fotoğrafını optiKA'ya gönderin.")
        hata_kaydet(str(e))
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                     # sessiz (pythonw) çalışırken bile iz bırak
        import traceback
        log("BEKLENMEYEN HATA  " + repr(e) + "\n" + traceback.format_exc())
        ilerle(100, f"Beklenmeyen hata: {e}"[:150], bitti=True, ok=False)
        sys.exit(1)
