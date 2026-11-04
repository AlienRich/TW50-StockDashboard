# 台股加權指數與 0050 戰情即時儀表板 (TAIEX & Yuanta Taiwan 50 Live Terminal)

極致輕量、零外部資料庫依賴的台股戰情監控面板。整合現代暗黑操盤介面（Tailwind CSS、TradingView Lightweight Charts、Apache ECharts、Lucide 圖標），並具備本地代理（Local Proxy）、防封鎖緩存限流（In-Memory Cache & Rate Limiter）、非同步即時金融串流（Server-Sent Events, SSE）及量化多空機率推演引擎。

---

## 🌟 功能亮點

1. **零外部資料庫與本機代理架構 (Zero-DB Local Proxy)**
   - 監聽 `127.0.0.1:8000`，徹底解決瀏覽器直接呼叫金融 API 的 CORS 跨域限制與 IP 阻擋問題。
   - 具備 5~10 秒內存緩存（In-Memory Cache）與限流保護，避免打爆公開資料源。
   - 伺服器發送事件（Server-Sent Events, SSE）端點 `/api/stream`，毫秒級推播最新跳動。

2. **加權指數 (TAIEX) 專業 K 線圖 (TradingView Lightweight Charts)**
   - 繪製 1 分鐘線（1m）與日 K 線（1d），台股慣例（紅漲、綠跌）。
   - 疊加 5MA (黃)、20MA (紫)、60MA (藍) 移動平均線。
   - 副圖精準繪製成交量柱（Volume Histogram）。
   - 支援 **Last Tick Flash**（最新價格跳動時頂部與背景閃爍紅/綠脈衝效果）。

3. **0050 權重熱力圖 (Apache ECharts Treemap)**
   - 涵蓋元大台灣50前 15 大市值權重成分股（台積電、鴻海、聯發科、富邦金、廣達、台達電、國泰金、中信金、日月光投控、兆豐金、聯電、統一、緯穎、智邦、中華電）。
   - 區塊面積依據真實市值權重劃分，顏色遵循台股規範（紅漲、綠跌、平盤深灰）。
   - 收到後端推播時動態平滑更新數值與顏色漸層。

4. **籌碼與信用看板 (Institutional & Margin Board)**
   - 即時拆解三大法人（外資、投信、自營商自行買賣、自營商避險、三大法人合計淨額）。
   - 全市場信用交易指標（融資餘額、融資單日增減、融券餘額、融券單日增減、市場券資比）。

5. **量化多空機率引擎 (Quant Probability Engine)**
   - 結合五大價量與籌碼維度：
     1. 均線排列強度（5MA / 20MA / 60MA 相對位階與多空排列）
     2. 盤中動量 RSI(14)
     3. 三大法人資金流向
     4. 盤中量價增溫配合度
     5. 融資融券安定度
   - 動態計算多空機率指示條（例如：多方 68% vs 空方 32%）與多空架構評級。

6. **離線容錯與盤後定盤機制 (Offline & After-Hours Resilience)**
   - 盤後或遇網路中斷時，自動提示「已載入最新收盤定盤價 / 離線模式」，確保畫面不崩潰。
   - 前端具備斷線自動重連機制。

---

## 📁 檔案架構

```text
twstock-dashboard/
├── main.py              # FastAPI 本機代理、數據爬取、量化引擎、SSE 推播服務
├── index.html           # 單一現代化前端儀表板 (Tailwind + TradingView + ECharts + Lucide)
├── requirements.txt     # Python 依賴清單 (FastAPI, Uvicorn, HTTPX)
├── run.sh               # Linux/macOS 啟動檔 (含動態路徑偵測、自動建立桌面捷徑與自癒機制)
├── start.bat            # Windows 啟動檔 (含動態路徑偵測與自動建立桌面捷徑)
├── icon.svg             # 專屬金融 K 線走勢圖圖示
└── README.md            # 專案說明與操作指引
```

7. **綠色便攜與自動建立桌面捷徑 (Portable & Self-Provisioning)**
   - **動態偵測路徑**：無論資料夾複製到任何電腦、隨身碟或目錄，執行當下自動偵測實際所在位置，不寫死絕對路徑。
   - **捷徑自動建立**：於新位置首次執行時，自動偵測並於桌面建立對應捷徑；若已存在且路徑相符則智慧跳過。
   - **環境自癒修復**：若資料夾路徑移動導致 Python 虛擬環境失效，啟動時自動檢測並重新健全化，免手動維護。

---

## 🚀 安裝與啟動方式

### 方法一：一鍵啟動（推薦）
```bash
cd /tmp/twstock-dashboard
./run.sh
```

### 方法二：手動安裝與啟動
1. 建立並啟動 Python 虛擬環境：
```bash
cd /tmp/twstock-dashboard
python3 -m venv .venv
source .venv/bin/activate
```

2. 安裝極簡依賴：
```bash
pip install -r requirements.txt
```

3. 啟動後端代理服務：
```bash
python main.py
```
或使用 Uvicorn：
```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

4. 開啟瀏覽器訪問儀表板：
👉 **http://127.0.0.1:8000**
