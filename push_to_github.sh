#!/usr/bin/env bash
# ==============================================================================
# 一鍵推送到 GitHub 互動式小幫手
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "===================================================="
echo "🚀 準備將台股加權指數與 0050 戰情室專案推送到 GitHub"
echo "===================================================="

# 1. 檢查是否已設定 Git 帳號與信箱
if ! git config user.name >/dev/null 2>&1 || ! git config user.email >/dev/null 2>&1; then
    echo "⚠️ 尚未設定 Git 身份資訊，請先輸入："
    read -p "請輸入您的 GitHub 用戶名稱 (例如 Alex731): " GIT_USER
    read -p "請輸入您的 GitHub 電子郵件 (例如 alex@example.com): " GIT_EMAIL
    git config --global user.name "$GIT_USER"
    git config --global user.email "$GIT_EMAIL"
    echo "✅ Git 身份設定完成！"
    echo "----------------------------------------------------"
fi

# 2. 初始化 Git 與啟用憑證記憶 (Credential Helper)
if [ ! -d ".git" ]; then
    echo "📦 初始化本地 Git 儲存庫..."
    git init
    git branch -M main
fi
# 啟用憑證記憶：只要輸入一次 Token，未來終端機與背景推送自動免密碼！
git config credential.helper store

# 3. 檢查或設定 GitHub 遠端儲存庫網址
CURRENT_REMOTE="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$CURRENT_REMOTE" ]; then
    echo "📌 請先至 https://github.com/new 建立一個全新 Repository"
    echo "   （提示：請勿勾選 Add a README、.gitignore 或 License）"
    echo ""
    read -p "請貼上您的 GitHub 儲存庫網址 (例如 https://github.com/帳號/twstock-dashboard.git): " REPO_URL
    if [ -z "$REPO_URL" ]; then
        echo "❌ 未輸入網址，取消推送。"
        exit 1
    fi
    git remote add origin "$REPO_URL"
else
    echo "🔗 目前已連接的遠端網址: $CURRENT_REMOTE"
fi

# 4. 加入檔案並提交
echo "📦 正在打包檔案並建立 Commit..."
git add .
git commit -m "feat: 初次發布台股加權指數與 0050 戰情室儀表板" || echo "（檔案已是最新，無額外變更）"

# 5. 推送到 GitHub
echo "🚀 正在推送到 GitHub main 分支..."
echo "💡 提示：若終端機要求輸入密碼 (Password)，請貼上您的 GitHub Personal Access Token (PAT)"
git push -u origin main

echo "===================================================="
echo "🎉 恭喜！專案已成功推送到 GitHub！"
echo "===================================================="
