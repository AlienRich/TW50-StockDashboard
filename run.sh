#!/usr/bin/env bash
# ==============================================================================
# 台股加權指數與 0050 戰情即時儀表板啟動器
# 具備動態位置偵測、環境自癒修復、以及桌面捷徑自動建立與維護功能
# ==============================================================================

# 1. 動態偵測當前執行位置（Portable Path Detection）
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "===================================================="
echo "📍 專案執行路徑: $DIR"

# 2. 自動偵測與建立桌面捷徑 (Desktop Shortcut Auto-Provisioning)
DESKTOP_DIR=""
if which xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null)"
fi
if [ -z "$DESKTOP_DIR" ] || [ ! -d "$DESKTOP_DIR" ]; then
    if [ -d "$HOME/桌面" ]; then
        DESKTOP_DIR="$HOME/桌面"
    elif [ -d "$HOME/Desktop" ]; then
        DESKTOP_DIR="$HOME/Desktop"
    fi
fi

if [ -n "$DESKTOP_DIR" ] && [ -d "$DESKTOP_DIR" ]; then
    DESKTOP_SHORTCUT="$DESKTOP_DIR/twstock-dashboard.desktop"
    NEED_SHORTCUT_UPDATE=0
    
    # 檢查捷徑是否存在
    if [ ! -f "$DESKTOP_SHORTCUT" ]; then
        NEED_SHORTCUT_UPDATE=1
    else
        # 若捷徑已存在，檢查其執行的路徑是否指向目前目錄
        if ! grep -q "$DIR/run.sh" "$DESKTOP_SHORTCUT" 2>/dev/null; then
            NEED_SHORTCUT_UPDATE=1
        fi
    fi

    # 若需要建立或更新捷徑
    if [ $NEED_SHORTCUT_UPDATE -eq 1 ]; then
        echo "📌 偵測到桌面捷徑不存在或路徑需要同步，正在自動建立桌面捷徑..."
        cat << EOF > "$DESKTOP_SHORTCUT"
[Desktop Entry]
Version=1.0
Type=Application
Name=台股與0050戰情室
Comment=台股加權指數與 0050 戰情即時儀表板
Exec=gnome-terminal -- "$DIR/run.sh"
Icon=$DIR/icon.svg
Terminal=false
Categories=Finance;Network;
StartupNotify=true
EOF
        chmod +x "$DESKTOP_SHORTCUT"
        gio set "$DESKTOP_SHORTCUT" metadata::trusted true 2>/dev/null || true
        echo "✅ 已成功建立桌面捷徑: $DESKTOP_SHORTCUT"
    fi
fi

# 3. 虛擬環境健全度與自癒檢查 (Auto-healing Virtual Environment)
NEED_VENV_REBUILD=0
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/python3" ]; then
    NEED_VENV_REBUILD=1
else
    # 檢查 .venv 內部直譯器是否指向當前目錄
    VENV_PIP_SHEBANG="$(head -n 1 .venv/bin/pip 2>/dev/null | sed -e 's/^#!//')"
    if [[ "$VENV_PIP_SHEBANG" != *"$DIR"* ]] || ! .venv/bin/python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
        NEED_VENV_REBUILD=1
    fi
fi

if [ $NEED_VENV_REBUILD -eq 1 ]; then
    echo "⚡ 偵測到環境需要初始化或路徑轉移，正在自動修復 .venv..."
    rm -rf .venv
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    echo "✅ 虛擬環境修復完成！"
fi

# 4. 瀏覽器開啟函式
open_browser() {
    URL="http://127.0.0.1:8000"
    if which xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 &
    elif which brave-browser >/dev/null 2>&1; then
        brave-browser "$URL" >/dev/null 2>&1 &
    elif which google-chrome >/dev/null 2>&1; then
        google-chrome "$URL" >/dev/null 2>&1 &
    elif which firefox >/dev/null 2>&1; then
        firefox "$URL" >/dev/null 2>&1 &
    fi
}

# 5. 檢查 8000 埠是否已有服務在運行 (加入 --noproxy 確保不受本機代理干擾)
if lsof -i :8000 >/dev/null 2>&1 || curl -s --noproxy "*" -m 1 http://127.0.0.1:8000/ >/dev/null 2>&1; then
    echo "📡 台股戰情室服務已在背景執行中！"
    echo "🌐 正在為您開啟瀏覽器: http://127.0.0.1:8000"
    echo "===================================================="
    open_browser
    sleep 2
    exit 0
fi

# 6. 背景排程在 1.5 秒後自動彈出瀏覽器
(sleep 1.5 && open_browser) &

echo "🚀 正在啟動台股加權指數與 0050 戰情即時儀表板..."
echo "📡 服務網址: http://127.0.0.1:8000"
echo "💡 提示：關閉此終端機視窗即可停止服務"
echo "===================================================="

# 7. 啟動服務 (使用 active 的 python -m uvicorn，最穩定相容)
source .venv/bin/activate
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ 服務異常結束 (代碼: $EXIT_CODE)，請按 Enter 鍵關閉視窗..."
    read -r
fi
