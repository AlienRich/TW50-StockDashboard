@echo off
chcp 65001 >nul
title 台股加權指數與 0050 戰情即時儀表板

REM 1. 動態偵測當前執行位置（Portable Path Detection）
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"
cd /d "%APP_DIR%"

echo ====================================================
echo  台股加權指數與 0050 戰情即時儀表板
echo  專案執行位置: %APP_DIR%
echo ====================================================

REM 2. 自動檢查與建立桌面捷徑 (Desktop Shortcut Auto-Provisioning)
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "SHORTCUT_PATH=%DESKTOP_DIR%\台股與0050戰情室.lnk"

if not exist "%SHORTCUT_PATH%" (
    echo [提示] 偵測到桌面尚未建立捷徑，正在自動建立...
    powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%APP_DIR%\start.bat'; $s.WorkingDirectory = '%APP_DIR%'; $s.IconLocation = '%APP_DIR%\icon.ico'; $s.Save()" 2>nul
    echo [成功] 已在桌面建立「台股與0050戰情室」捷徑！
)

REM 3. 虛擬環境健全度與自癒檢查
if not exist "%APP_DIR%\.venv\Scripts\python.exe" (
    echo [提示] 正在初始化 Python 虛擬環境...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

REM 4. 開啟瀏覽器並啟動服務
echo [提示] 正在開啟瀏覽器...
start http://127.0.0.1:8000

echo [提示] 正在啟動伺服器...
python -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
