@echo off
setlocal
cd /d "%~dp0"
rem =====================================================================
rem  optiKA Nobet Panosu v1.0.0 - TEK DOSYA (Windows)
rem  Ilk calistirmada kurar (Python paketleri, otomatik guncelleme, masaustu simgesi),
rem  sonraki her acilista: guncel listeyi alir + panoyu acar.
rem  Masaustundeki "Nobet Panosu" simgesi bu dosyayi calistirir.
rem  Yeniden kurmak icin:  NOBET_PANOSU_Windows.bat kur
rem =====================================================================
set SURUM=5
set ARALIK=5
set "BU=%~f0"
set "DIZ=%~dp0"

set "KUR="
if /i "%~1"=="kur" set KUR=1
if not exist "%DIZ%.kurulum\surum_%SURUM%.txt" set KUR=1
if not exist "%DIZ%.kurulum\pythonw.txt" set KUR=1
schtasks /query /tn "NobetPanosuGuncelle" >nul 2>&1 || set KUR=1
if defined KUR (
  call :kurulum
  if errorlevel 1 exit /b 1
)

set /p PYW=<"%DIZ%.kurulum\pythonw.txt"
if not exist "%PYW%" set /p PYW=<"%DIZ%.kurulum\python.txt"
>>"%DIZ%guncelle.log" echo %date% %time:~0,8%  Baslatici: acilis guncellemesi "%PYW%" ile baslatiliyor

rem ---- 1) Guncel listeyi arka planda al: pano giris ekraninda % cubugu olarak gosterir ----
start "" "%PYW%" "%DIZ%guncelle.py" --ilerleme
rem Panodaki "Simdi guncelle" dugmesi icin yerel yardimci (yalnizca bu bilgisayar): eskisini kapat, bu klasorden yenisini baslat
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*guncelle.py*--yardimci*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
start "" "%PYW%" "%DIZ%guncelle.py" --yardimci

rem ---- 2) Panoyu ac: once Chrome, yoksa Edge (normal pencere; F = tam ekran ac/kapat, A = ilce secimi) ----
set "TARAYICI="
for %%B in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LocalAppData%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe") do if not defined TARAYICI if exist %%B set "TARAYICI=%%~B"
if not defined TARAYICI (
  echo Chrome veya Edge bulunamadi.
  pause
  exit /b 1
)
set "SAYFA=%DIZ%nobet_panosu.html"
set "SAYFA=%SAYFA:\=/%"
start "" "%TARAYICI%" --app="file:///%SAYFA%" --start-maximized --no-first-run --noerrdialogs --disable-session-crashed-bubble --disable-features=Translate --autoplay-policy=no-user-gesture-required --user-data-dir="%DIZ%tarayici_profil"
rem Pencereyi one al ve F13 gonder: pano kayitli tercihe gore kendiliginden tam ekrana gecer
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep 6; $w=New-Object -ComObject WScript.Shell; $null=$w.AppActivate('Eczaneler'); Start-Sleep -Milliseconds 400; $w.SendKeys('{F13}')"
exit /b 0


:kurulum
title optiKA Nobet Panosu - kurulum
echo.
echo  optiKA Nobet Panosu kuruluyor (ilk calistirma, 1-2 dakika surer)...
echo.
rem ---- Python bul; yoksa kendisi kursun (winget, olmazsa python.org) ----
call :pythonbul
if not defined PY call :pythonkur
if not defined PY goto :pythonyok
set "PYW=%PY:python.exe=pythonw.exe%"
rem Microsoft Store Python: gercek yolu zamanlanmis gorevden calismaz, kisayolu kullan
echo %PY% | find /i "WindowsApps" >nul && if exist "%LocalAppData%\Microsoft\WindowsApps\pythonw.exe" set "PYW=%LocalAppData%\Microsoft\WindowsApps\pythonw.exe"
if not exist "%PYW%" set "PYW=%PY%"
echo  Python: %PY%

"%PY%" -m pip install --disable-pip-version-check -q requests beautifulsoup4 segno
if errorlevel 1 (
  echo.
  echo [HATA] Python paketleri kurulamadi. Internet baglantisini kontrol edip tekrar deneyin.
  pause
  exit /b 1
)
if not exist "%DIZ%.kurulum" mkdir "%DIZ%.kurulum"
attrib +h "%DIZ%.kurulum" >nul 2>&1
>"%DIZ%.kurulum\python.txt" echo %PY%
>"%DIZ%.kurulum\pythonw.txt" echo %PYW%

rem ---- Indirilen dosyalarin "internetten geldi" engelini kaldir ----
powershell -NoProfile -Command "Get-ChildItem -Path '%DIZ%' -Recurse | Unblock-File" >nul 2>&1

rem ---- Otomatik guncelleme: gorev 5 dk da bir uyanir, oda sitesine yalnizca 08:30 ve 18:00 de gider ----
schtasks /create /tn "NobetPanosuGuncelle" /tr "\"%PYW%\" \"%DIZ%guncelle.py\" --zamanli --aralik %ARALIK%" /sc minute /mo %ARALIK% /f >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -MultipleInstances IgnoreNew; Set-ScheduledTask -TaskName NobetPanosuGuncelle -Settings $s | Out-Null" >nul 2>&1

rem ---- Ekran ve bilgisayar uykuya gecmesin ----
powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
rem Ekran koruyucu kapali (pano saatlerce dokunulmadan ekranda kalacak)
reg add "HKCU\Control Panel\Desktop" /v ScreenSaveActive /t REG_SZ /d 0 /f >nul
reg add "HKCU\Control Panel\Desktop" /v ScreenSaverIsSecure /t REG_SZ /d 0 /f >nul
reg delete "HKCU\Control Panel\Desktop" /v SCRNSAVE.EXE /f >nul 2>&1

rem ---- Panodaki "Simdi guncelle" ve "Saatleri kaydet" dugmeleri icin nobetpanosu:// baglantisi (yonetici izni gerekmez) ----
reg add "HKCU\Software\Classes\nobetpanosu" /ve /d "URL:Nobet Panosu" /f >nul
reg add "HKCU\Software\Classes\nobetpanosu" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\nobetpanosu\DefaultIcon" /ve /d "\"%DIZ%simge\optika.ico\"" /f >nul
reg add "HKCU\Software\Classes\nobetpanosu\shell\open\command" /ve /d "\"%PYW%\" \"%DIZ%guncelle.py\" --ilerleme \"%%1\"" /f >nul

rem ---- Masaustu simgesi + Windows acilinca otomatik baslat ----
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $ad='N'+[char]0xF6+'bet Panosu.lnk'; foreach($k in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Startup'))){ $s=$w.CreateShortcut((Join-Path $k $ad)); $s.TargetPath='%BU%'; $s.WorkingDirectory='%DIZ%'; $s.IconLocation='%DIZ%simge\optika.ico,0'; $s.WindowStyle=7; $s.Description='optiKA Nobet Panosu'; $s.Save() }"

echo.
echo ==========================================
"%PY%" "%DIZ%guncelle.py" --kod
echo Bu kodu lisans icin optiKA ya iletin.
echo ==========================================
>"%DIZ%.kurulum\surum_%SURUM%.txt" echo ok
echo.
echo  Kurulum tamam. Bundan sonra masaustundeki "Nobet Panosu" simgesini kullanin.
echo  Pano simdi aciliyor...
timeout /t 8 >nul
exit /b 0

:pythonbul
set "PY="
for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
if defined PY if not exist "%PY%" set "PY="
if not defined PY for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
if defined PY if not exist "%PY%" set "PY="
rem Yeni kurulduysa PATH bu pencerede henuz yenilenmemistir: bilinen klasorlere de bak
if not defined PY for /d %%d in ("%LocalAppData%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if exist "%%~d\python.exe" set "PY=%%~d\python.exe"
exit /b 0

:pythonkur
echo.
echo  Python bulunamadi - otomatik kuruluyor (2-5 dakika surebilir, pencereyi kapatmayin)...
where winget >nul 2>&1 && winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :pythonbul
if defined PY exit /b 0
echo  winget ile kurulamadi; Python python.org adresinden indiriliyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; $f=Join-Path $env:TEMP 'python-3.12.10-amd64.exe'; Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $f -UseBasicParsing; Start-Process $f -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1' -Wait"
call :pythonbul
exit /b 0

:pythonyok
echo.
echo [HATA] Python otomatik kurulamadi (internet baglantisini kontrol edin).
echo        Elle kurmak icin: https://www.python.org/downloads/ - kurulumda "Add python.exe to PATH" isaretli olsun.
echo        Sonra bu dosyayi tekrar calistirin.
pause
exit /b 1
