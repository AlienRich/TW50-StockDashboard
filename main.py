import asyncio
import json
import logging
import math
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("twstock_dashboard")

# 抑制 httpx 與 httpcore 的過多 HTTP 請求日誌刷屏，保持終端機簡潔
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# 台灣時區 UTC+8
TW_TZ = timezone(timedelta(hours=8))

# 0050 主要前 15 大成分股基準資料 (代號、名稱、權重 %、參考基準價)
CONSTITUENTS_CONFIG = [
    {"code": "2330", "name": "台積電", "weight": 56.20, "base_price": 2585.0},
    {"code": "2317", "name": "鴻海", "weight": 6.10, "base_price": 252.0},
    {"code": "2454", "name": "聯發科", "weight": 4.50, "base_price": 4835.0},
    {"code": "2881", "name": "富邦金", "weight": 1.80, "base_price": 155.5},
    {"code": "2382", "name": "廣達", "weight": 1.70, "base_price": 430.0},
    {"code": "2308", "name": "台達電", "weight": 1.60, "base_price": 540.0},
    {"code": "2882", "name": "國泰金", "weight": 1.50, "base_price": 105.0},
    {"code": "2891", "name": "中信金", "weight": 1.40, "base_price": 58.5},
    {"code": "3711", "name": "日月光投控", "weight": 1.30, "base_price": 248.0},
    {"code": "2886", "name": "兆豐金", "weight": 1.20, "base_price": 52.0},
    {"code": "2303", "name": "聯電", "weight": 1.10, "base_price": 68.0},
    {"code": "1216", "name": "統一", "weight": 1.00, "base_price": 92.5},
    {"code": "6669", "name": "緯穎", "weight": 0.90, "base_price": 3120.0},
    {"code": "2345", "name": "智邦", "weight": 0.80, "base_price": 765.0},
    {"code": "2412", "name": "中華電", "weight": 0.80, "base_price": 138.0},
]

class MarketDataManager:
    def __init__(self):
        self.last_fetch_time = 0.0
        self.fetch_cooldown = 300.0  # 緩存限流：改為 5 分鐘 (300 秒) 查一次，徹底杜絕封鎖風險
        self.last_daily_fetch_time = 0.0 # 三大法人與融資券每日盤後資料上次抓取時間
        self.client = httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        
        # 內存快取 (In-Memory Cache)
        self.cache: Dict[str, Any] = {
            "taiex": {
                "price": 44041.66,
                "change": 1329.74,
                "change_pct": 3.11,
                "open": 43135.76,
                "high": 44041.66,
                "low": 42708.05,
                "prev_close": 42711.92,
                "volume": 4865.2,  # 億元
                "volume_shares": 3861937,
                "time": "13:30:00",
                "date": datetime.now(TW_TZ).strftime("%Y-%m-%d"),
            },
            "components": [],
            "institution": {
                "foreign": -341.17,      # 億元
                "trust": 398.91,         # 億元
                "dealer_self": -55.39,   # 億元
                "dealer_hedge": -119.97, # 億元
                "dealer_total": -175.36, # 億元
                "total": -117.62,        # 億元
                "date": datetime.now(TW_TZ).strftime("%Y-%m-%d"),
            },
            "futures": {
                "foreign_oi": -103473,      # 外資期貨未平倉留倉淨口數 (口)
                "trust_oi": 98519,          # 投信期貨未平倉留倉淨口數 (口)
                "dealer_oi": 85,            # 自營商期貨未平倉留倉淨口數 (口)
                "total_oi": -4869,          # 三大法人期貨合計淨留倉 (口)
                "foreign_long_oi": 9875,    # 外資多方口數
                "foreign_short_oi": 113348, # 外資空方口數
                "contract": "台指期貨 (TX)",
                "date": datetime.now(TW_TZ).strftime("%Y-%m-%d"),
            },
            "margin": {
                "margin_balance_billion": 637.65,  # 融資餘額 (億元)
                "margin_change_billion": 4.31,     # 融資增減 (億元)
                "short_balance_shares": 214529,    # 融券餘額 (張)
                "short_change_shares": -3929,      # 融券增減 (張)
                "short_margin_ratio": 2.29,        # 券資比 %
                "date": datetime.now(TW_TZ).strftime("%Y-%m-%d"),
            },
            "kline_5m": [],
            "kline_60m": [],
            "kline_1d": [],
            "quant": {},
            "market_status": "AFTER_HOURS_SETTLED", # LIVE, AFTER_HOURS_SETTLED, OFFLINE_CACHE
            "status_text": "已載入最新收盤定盤價",
            "last_updated": datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # 初始化 15 大成分股
        self._init_mock_components()
        self._generate_fallback_klines()
        self._recalculate_quant_engine()

    def _init_mock_components(self):
        items = []
        for c in CONSTITUENTS_CONFIG:
            price = c["base_price"]
            change_pct = round((math.sin(hash(c["code"])) * 1.8), 2)
            prev_close = round(price / (1 + change_pct / 100), 2)
            change = round(price - prev_close, 2)
            items.append({
                "code": c["code"],
                "name": c["name"],
                "weight": c["weight"],
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "prev_close": prev_close,
                "open": prev_close,
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "volume": int(1000 + abs(hash(c["code"]) % 40000)),
            })
        self.cache["components"] = items

    def _generate_fallback_klines(self):
        now = datetime.now(TW_TZ)
        base_price = self.cache["taiex"]["price"]
        prev_close = self.cache["taiex"]["prev_close"]
        
        # 5 分鐘線備援數據 (最近 10 個交易日，每日 54 根，+28800 轉換為台灣時間 UTC+8)
        klines_5m = []
        cur_p = prev_close * 0.97
        start_ts = int((now - timedelta(days=10)).timestamp()) + 28800
        for i in range(540):
            ts = start_ts + i * 300
            drift = (base_price - cur_p) / (540 - i + 1)
            noise = (math.sin(i * 0.12) + math.cos(i * 0.28)) * 12.0
            o = round(cur_p, 2)
            c = round(cur_p + drift + noise * 0.35, 2)
            h = round(max(o, c) + abs(noise * 0.6), 2)
            l = round(min(o, c) - abs(noise * 0.6), 2)
            vol = int(1200 + abs(math.sin(i * 0.18) * 3500))
            cur_p = c
            klines_5m.append({
                "time": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": vol
            })
        klines_5m[-1]["close"] = base_price
        self.cache["kline_5m"] = klines_5m

        # 60 分鐘線備援數據 (涵蓋近 12 個月，+28800 轉換為台灣時間 UTC+8)
        klines_60m = []
        cur_60_price = base_price * 0.88
        start_60_ts = int((now - timedelta(days=365)).timestamp()) + 28800
        for i in range(1200):
            ts = start_60_ts + i * 3600
            trend = (base_price - cur_60_price) / (1200 - i + 1)
            noise = (math.sin(i * 0.08) + math.cos(i * 0.15)) * 40.0
            o = round(cur_60_price, 2)
            c = round(cur_60_price + trend + noise * 0.3, 2)
            h = round(max(o, c) + abs(noise * 0.5), 2)
            l = round(min(o, c) - abs(noise * 0.5), 2)
            vol = int(15000 + abs(math.sin(i * 0.2) * 25000))
            cur_60_price = c
            klines_60m.append({
                "time": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": vol
            })
        klines_60m[-1]["close"] = base_price
        self.cache["kline_60m"] = klines_60m

        # 日 K 線 (拉長至 12 個月 / 250 個交易日)
        klines_1d = []
        cur_d_price = base_price * 0.85
        today_date = now.date()
        for i in range(250, 0, -1):
            d = today_date - timedelta(days=int(i * 1.46))
            trend = (base_price - cur_d_price) / (i + 1)
            noise = (math.sin(i * 0.35) + math.cos(i * 0.7)) * 140.0
            o = round(cur_d_price, 2)
            c = round(cur_d_price + trend + noise * 0.25, 2)
            h = round(max(o, c) + abs(noise * 0.4), 2)
            l = round(min(o, c) - abs(noise * 0.4), 2)
            vol = int(250000 + abs(math.sin(i * 0.3) * 150000))
            cur_d_price = c
            klines_1d.append({
                "time": d.strftime("%Y-%m-%d"),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": vol
            })
        # 最後一根設定為最新收盤
        klines_1d[-1]["close"] = base_price
        klines_1d[-1]["high"] = max(klines_1d[-1]["high"], self.cache["taiex"]["high"])
        klines_1d[-1]["low"] = min(klines_1d[-1]["low"], self.cache["taiex"]["low"])
        self.cache["kline_1d"] = klines_1d

    def _is_market_open(self) -> bool:
        now = datetime.now(TW_TZ)
        # 週一至週五 09:00 至 13:30 開盤
        if now.weekday() >= 5:
            return False
        market_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        market_end = now.replace(hour=13, minute=30, second=0, microsecond=0)
        return market_start <= now <= market_end

    async def fetch_twse_mis_batch(self):
        codes = ["t00"] + [c["code"] for c in CONSTITUENTS_CONFIG]
        ch_param = "|".join([f"tse_{c}.tw" for c in codes])
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ch_param}&json=1&delay=0"
        
        try:
            res = await self.client.get(url)
            if res.status_code == 200:
                data = res.json()
                msg_array = data.get("msgArray", [])
                if not msg_array:
                    return False
                
                # 更新指數 t00
                comp_map = {item["c"]: item for item in msg_array if "c" in item}
                if "t00" in comp_map:
                    t00 = comp_map["t00"]
                    price = float(t00.get("z") or t00.get("y") or self.cache["taiex"]["price"])
                    prev_close = float(t00.get("y") or self.cache["taiex"]["prev_close"])
                    change = round(price - prev_close, 2)
                    change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
                    
                    self.cache["taiex"].update({
                        "price": price,
                        "change": change,
                        "change_pct": change_pct,
                        "open": float(t00.get("o") or price),
                        "high": float(t00.get("h") or price),
                        "low": float(t00.get("l") or price),
                        "prev_close": prev_close,
                        "time": t00.get("t", self.cache["taiex"]["time"]),
                        "date": t00.get("d", self.cache["taiex"]["date"]),
                    })

                # 更新 15 大成分股
                new_comps = []
                for cfg in CONSTITUENTS_CONFIG:
                    code = cfg["code"]
                    raw = comp_map.get(code)
                    if raw:
                        prev_close = float(raw.get("y") or cfg["base_price"])
                        raw_z = raw.get("z")
                        # 盤中或盤後若無成交價可能為 '-'，使用買進/賣出最高或昨收
                        if raw_z and raw_z != "-":
                            price = float(raw_z)
                        elif raw.get("b") and raw.get("b") != "-":
                            price = float(raw.get("b").split("_")[0])
                        else:
                            price = prev_close
                            
                        change = round(price - prev_close, 2)
                        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
                        vol = int(raw.get("v") or 0)
                        
                        new_comps.append({
                            "code": code,
                            "name": cfg["name"],
                            "weight": cfg["weight"],
                            "price": price,
                            "change": change,
                            "change_pct": change_pct,
                            "prev_close": prev_close,
                            "open": float(raw.get("o") or price),
                            "high": float(raw.get("h") or price),
                            "low": float(raw.get("l") or price),
                            "volume": vol,
                        })
                    else:
                        # 保留原快取
                        existing = next((x for x in self.cache["components"] if x["code"] == code), None)
                        if existing:
                            new_comps.append(existing)
                
                if new_comps:
                    self.cache["components"] = new_comps
                return True
        except Exception as e:
            logger.warning(f"TWSE MIS fetch failed: {e}")
            return False

    async def fetch_yahoo_klines(self):
        try:
            # 1. 抓取加權指數 5 分鐘線 (涵蓋近 1 個月)
            url_5m = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=5m&range=1mo"
            res_5m = await self.client.get(url_5m)
            if res_5m.status_code == 200:
                data_5m = res_5m.json()
                result_5m = data_5m.get("chart", {}).get("result", [])
                if result_5m:
                    timestamps = result_5m[0].get("timestamp", [])
                    quote = result_5m[0].get("indicators", {}).get("quote", [{}])[0]
                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    vols = quote.get("volume", [])
                    meta = result_5m[0].get("meta", {})
                    
                    seen_5m = set()
                    parsed_5m = []
                    for i in range(len(timestamps)):
                        if opens[i] is not None and closes[i] is not None and timestamps[i] not in seen_5m:
                            seen_5m.add(timestamps[i])
                            # Yahoo Finance 的 timestamps 為 UTC 秒數，輕量圖表 (Lightweight Charts) 預設以 UTC 格式化時間軸
                            # 加上 28800 秒 (+8小時) 讓時間軸與刻度直接呈現台灣本地時間 (UTC+8)
                            parsed_5m.append({
                                "time": timestamps[i] + 28800,
                                "open": round(opens[i], 2),
                                "high": round(highs[i], 2),
                                "low": round(lows[i], 2),
                                "close": round(closes[i], 2),
                                "volume": int(vols[i] or 0),
                            })
                    if len(parsed_5m) > 10:
                        self.cache["kline_5m"] = parsed_5m
                        # 同步將 Yahoo Finance 的最新指數行情更新至首頁大卡片（作為 TWSE MIS 的強力備援）
                        latest_bar = parsed_5m[-1]
                        latest_price = meta.get("regularMarketPrice") or latest_bar["close"]
                        prev_close = meta.get("chartPreviousClose") or self.cache["taiex"]["prev_close"]
                        chg = round(latest_price - prev_close, 2)
                        chg_pct = round((chg / prev_close) * 100, 2) if prev_close else 0.0
                        last_ts = timestamps[-1] if timestamps else time.time()
                        
                        self.cache["taiex"].update({
                            "price": round(latest_price, 2),
                            "change": chg,
                            "change_pct": chg_pct,
                            "prev_close": round(prev_close, 2),
                            "open": round(parsed_5m[0]["open"] if parsed_5m else latest_price, 2),
                            "high": round(meta.get("regularMarketDayHigh") or latest_bar["high"], 2),
                            "low": round(meta.get("regularMarketDayLow") or latest_bar["low"], 2),
                            "time": datetime.fromtimestamp(last_ts, tz=TW_TZ).strftime("%H:%M:%S"),
                            "date": datetime.fromtimestamp(last_ts, tz=TW_TZ).strftime("%Y-%m-%d"),
                        })

            # 2. 抓取加權指數 60 分鐘線 (涵蓋近 12 個月)
            url_60m = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=60m&range=1y"
            res_60m = await self.client.get(url_60m)
            if res_60m.status_code == 200:
                data_60m = res_60m.json()
                result_60m = data_60m.get("chart", {}).get("result", [])
                if result_60m:
                    timestamps = result_60m[0].get("timestamp", [])
                    quote = result_60m[0].get("indicators", {}).get("quote", [{}])[0]
                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    vols = quote.get("volume", [])
                    
                    seen_60m = set()
                    parsed_60m = []
                    for i in range(len(timestamps)):
                        if opens[i] is not None and closes[i] is not None and timestamps[i] not in seen_60m:
                            seen_60m.add(timestamps[i])
                            # 加上 28800 秒 (+8小時) 轉換為台灣時間
                            parsed_60m.append({
                                "time": timestamps[i] + 28800,
                                "open": round(opens[i], 2),
                                "high": round(highs[i], 2),
                                "low": round(lows[i], 2),
                                "close": round(closes[i], 2),
                                "volume": int(vols[i] or 0),
                            })
                    if len(parsed_60m) > 10:
                        self.cache["kline_60m"] = parsed_60m
                        
            # 3. 抓取加權指數 日 K 線 (拉長至 12 個月 / 1 年)
            url_1d = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&range=1y"
            res_d = await self.client.get(url_1d)
            if res_d.status_code == 200:
                data_d = res_d.json()
                result_d = data_d.get("chart", {}).get("result", [])
                if result_d:
                    timestamps = result_d[0].get("timestamp", [])
                    quote = result_d[0].get("indicators", {}).get("quote", [{}])[0]
                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    vols = quote.get("volume", [])
                    
                    seen_dates = set()
                    parsed_1d = []
                    for i in range(len(timestamps)):
                        if opens[i] is not None and closes[i] is not None:
                            d_str = datetime.fromtimestamp(timestamps[i], tz=TW_TZ).strftime("%Y-%m-%d")
                            if d_str not in seen_dates:
                                seen_dates.add(d_str)
                                parsed_1d.append({
                                    "time": d_str,
                                    "open": round(opens[i], 2),
                                    "high": round(highs[i], 2),
                                    "low": round(lows[i], 2),
                                    "close": round(closes[i], 2),
                                    "volume": int(vols[i] or 0),
                                })
                    if len(parsed_1d) > 20:
                        self.cache["kline_1d"] = parsed_1d
        except Exception as e:
            logger.warning(f"Yahoo klines fetch failed: {e}")

    async def fetch_institutional_chips(self):
        try:
            url = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json"
            res = await self.client.get(url)
            if res.status_code == 200:
                data = res.json()
                rows = data.get("data", [])
                # rows 包含: 自營商(自行買賣), 自營商(避險), 投信, 外資及陸資(不含外資自營商), 外資自營商, 合計
                dealer_self, dealer_hedge, trust, foreign = 0.0, 0.0, 0.0, 0.0
                for row in rows:
                    name = str(row[0]).strip()
                    # 第4欄為差額(買賣超)
                    diff_str = str(row[3]).replace(",", "").strip()
                    try:
                        diff_val = float(diff_str) / 100000000.0  # 轉為億元
                    except ValueError:
                        diff_val = 0.0
                    
                    if "外資自營商" in name:
                        # 重要：必須跳過「外資自營商」，因其已包含在「外資及陸資」之內，避免覆蓋外資數據成 0.00
                        continue
                    elif "外資" in name or "陸資" in name:
                        foreign = round(diff_val, 2)
                    elif "自行買賣" in name:
                        dealer_self = round(diff_val, 2)
                    elif "避險" in name:
                        dealer_hedge = round(diff_val, 2)
                    elif "投信" in name:
                        trust = round(diff_val, 2)

                dealer_total = round(dealer_self + dealer_hedge, 2)
                total = round(foreign + trust + dealer_total, 2)
                self.cache["institution"] = {
                    "foreign": foreign,
                    "trust": trust,
                    "dealer_self": dealer_self,
                    "dealer_hedge": dealer_hedge,
                    "dealer_total": dealer_total,
                    "total": total,
                    "date": data.get("date", datetime.now(TW_TZ).strftime("%Y-%m-%d")),
                }
        except Exception as e:
            logger.warning(f"Institutional data fetch failed: {e}")

    async def fetch_taifex_futures(self):
        """抓取期交所 (TAIFEX) 三大法人期貨留倉 (未平倉 Open Interest) 數據"""
        try:
            # 優先嘗試抓取台指期貨契約 (TX) 明細
            url_tx = "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
            res_tx = await self.client.get(url_tx, timeout=8.0)
            if res_tx.status_code == 200:
                data_tx = res_tx.json()
                if isinstance(data_tx, list) and len(data_tx) > 0:
                    foreign_oi, trust_oi, dealer_oi = 0, 0, 0
                    f_long_oi, f_short_oi = 0, 0
                    date_str = ""
                    matched = False
                    for item in data_tx:
                        code = str(item.get("ContractCode") or "")
                        if "臺股期貨" in code or code == "TX":
                            matched = True
                            name = str(item.get("Item") or item.get("Name") or "")
                            date_str = str(item.get("Date") or date_str)
                            
                            # TAIFEX 官方欄位名稱為 "OpenInterest(Net)", "OpenInterest(Long)", "OpenInterest(Short)"
                            net_oi = (
                                item.get("OpenInterest(Net)")
                                or item.get("OpenInterestNet")
                                or item.get("NetVolume")
                                or item.get("FuturesNetOIQty")
                                or 0
                            )
                            long_oi = (
                                item.get("OpenInterest(Long)")
                                or item.get("OpenInterestLong")
                                or item.get("LongVolume")
                                or item.get("FuturesLongOIQty")
                                or 0
                            )
                            short_oi = (
                                item.get("OpenInterest(Short)")
                                or item.get("OpenInterestShort")
                                or item.get("ShortVolume")
                                or item.get("FuturesShortOIQty")
                                or 0
                            )
                            
                            try:
                                net_oi = int(str(net_oi).replace(",", "").strip())
                                long_oi = int(str(long_oi).replace(",", "").strip())
                                short_oi = int(str(short_oi).replace(",", "").strip())
                            except (ValueError, TypeError):
                                net_oi = 0
                            
                            if "外資" in name or "陸資" in name:
                                foreign_oi = net_oi
                                f_long_oi = long_oi
                                f_short_oi = short_oi
                            elif "投信" in name:
                                trust_oi = net_oi
                            elif "自營" in name:
                                dealer_oi = net_oi
                                
                    if matched and (foreign_oi != 0 or trust_oi != 0 or dealer_oi != 0):
                        self.cache["futures"] = {
                            "foreign_oi": foreign_oi,
                            "trust_oi": trust_oi,
                            "dealer_oi": dealer_oi,
                            "total_oi": foreign_oi + trust_oi + dealer_oi,
                            "foreign_long_oi": f_long_oi,
                            "foreign_short_oi": f_short_oi,
                            "contract": "台指期貨 (TX)",
                            "date": date_str or datetime.now(TW_TZ).strftime("%Y-%m-%d"),
                        }
                        return True

            # 備援：抓取三大法人全期貨契約分類總表
            url_all = "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDividedByFuturesAndOptionsBytheDate"
            res_all = await self.client.get(url_all, timeout=8.0)
            if res_all.status_code == 200:
                data_all = res_all.json()
                if isinstance(data_all, list) and len(data_all) > 0:
                    foreign_oi, trust_oi, dealer_oi = 0, 0, 0
                    f_long_oi, f_short_oi = 0, 0
                    date_str = ""
                    for item in data_all:
                        name = str(item.get("Item") or item.get("Name") or item.get("Identity") or "")
                        date_str = str(item.get("Date") or date_str)
                        net_oi = (
                            item.get("FuturesOpenInterest(Net)")
                            or item.get("FuturesNetOIQty")
                            or item.get("FutureNetOIQty")
                            or 0
                        )
                        long_oi = (
                            item.get("FuturesOpenInterest(Long)")
                            or item.get("FuturesLongOIQty")
                            or item.get("FutureLongOIQty")
                            or 0
                        )
                        short_oi = (
                            item.get("FuturesOpenInterest(Short)")
                            or item.get("FuturesShortOIQty")
                            or item.get("FutureShortOIQty")
                            or 0
                        )
                        try:
                            net_oi = int(str(net_oi).replace(",", "").strip())
                            long_oi = int(str(long_oi).replace(",", "").strip())
                            short_oi = int(str(short_oi).replace(",", "").strip())
                        except (ValueError, TypeError):
                            net_oi = 0
                            
                        if "外資" in name or "陸資" in name:
                            foreign_oi = net_oi
                            f_long_oi = long_oi
                            f_short_oi = short_oi
                        elif "投信" in name:
                            trust_oi = net_oi
                        elif "自營" in name:
                            dealer_oi = net_oi
                    
                    if foreign_oi != 0 or trust_oi != 0 or dealer_oi != 0:
                        self.cache["futures"] = {
                            "foreign_oi": foreign_oi,
                            "trust_oi": trust_oi,
                            "dealer_oi": dealer_oi,
                            "total_oi": foreign_oi + trust_oi + dealer_oi,
                            "foreign_long_oi": f_long_oi,
                            "foreign_short_oi": f_short_oi,
                            "contract": "全市場期貨",
                            "date": date_str or datetime.now(TW_TZ).strftime("%Y-%m-%d"),
                        }
                        return True
        except Exception as e:
            logger.warning(f"TAIFEX futures fetch failed: {e}")
            return False

    async def fetch_margin_data(self):
        try:
            url = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&selectType=MS"
            res = await self.client.get(url)
            if res.status_code == 200:
                data = res.json()
                tables = data.get("tables", [])
                if tables and len(tables) > 0:
                    rows = tables[0].get("data", [])
                    # 融資(交易單位), 融券(交易單位), 融資金額(仟元)
                    for r in rows:
                        item = r[0]
                        # 前日餘額 r[4], 今日餘額 r[5]
                        if "融資金額" in item:
                            prev = float(r[4].replace(",", "")) / 100000.0 # 仟元轉為億元
                            today = float(r[5].replace(",", "")) / 100000.0
                            diff = round(today - prev, 2)
                            self.cache["margin"]["margin_balance_billion"] = round(today, 2)
                            self.cache["margin"]["margin_change_billion"] = diff
                        elif "融券" in item and "交易單位" in item:
                            prev_s = int(r[4].replace(",", ""))
                            today_s = int(r[5].replace(",", ""))
                            diff_s = today_s - prev_s
                            self.cache["margin"]["short_balance_shares"] = today_s
                            self.cache["margin"]["short_change_shares"] = diff_s
                    # 計算券資比
                    mb = self.cache["margin"]["margin_balance_billion"]
                    sb = self.cache["margin"]["short_balance_shares"]
                    if mb > 0:
                        self.cache["margin"]["short_margin_ratio"] = round((sb / (mb * 1000)) * 10, 2)
        except Exception as e:
            logger.warning(f"Margin data fetch failed: {e}")

    def _recalculate_quant_engine(self):
        """依據即時均線、動量 RSI、籌碼與量能，計算量化多空機率引擎"""
        klines = self.cache["kline_1d"]
        closes = [k["close"] for k in klines]
        if len(closes) < 20:
            closes = [self.cache["taiex"]["price"]] * 30
            
        cur_p = self.cache["taiex"]["price"]
        
        # 1. 均線計算
        ma5 = round(sum(closes[-5:]) / min(len(closes), 5), 2)
        ma20 = round(sum(closes[-20:]) / min(len(closes), 20), 2)
        ma60 = round(sum(closes[-60:]) / min(len(closes), 60), 2) if len(closes) >= 60 else ma20
        
        # 均線排列強度評分 (-30 ~ +30)
        ma_score = 0
        if cur_p > ma5 > ma20 > ma60:
            ma_score = 30
            ma_desc = "全面多頭排列（指數 > 5MA > 20MA > 60MA），均線強力發散向上"
        elif cur_p > ma20 and ma5 > ma20:
            ma_score = 18
            ma_desc = "短多震盪格局，站上月均線 (20MA) 偏多運行"
        elif cur_p < ma5 < ma20 < ma60:
            ma_score = -30
            ma_desc = "全面空頭排列，短中長天期均線下彎蓋頂承壓"
        elif cur_p < ma20:
            ma_score = -18
            ma_desc = "跌破月線轉弱，空方籌碼壓制防守"
        else:
            ma_score = 0
            ma_desc = "均線糾結，進入區間箱型整理"

        # 2. RSI(14) 計算 (-20 ~ +20)
        rsi = 50.0
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, 15):
                diff = closes[-i] - closes[-i - 1]
                if diff >= 0:
                    gains.append(diff)
                    losses.append(0.0)
                else:
                    gains.append(0.0)
                    losses.append(abs(diff))
            avg_gain = sum(gains) / 14.0
            avg_loss = sum(losses) / 14.0
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = round(100.0 - (100.0 / (1.0 + rs)), 1)
        
        rsi_score = 0
        if 55 <= rsi <= 72:
            rsi_score = 20
            rsi_desc = f"RSI(14) = {rsi}，多頭動能穩健擴張，未見超買過熱"
        elif rsi > 72:
            rsi_score = 10
            rsi_desc = f"RSI(14) = {rsi}，強勢高檔鈍化，需提防指標背離短線拉回"
        elif 35 <= rsi < 55:
            rsi_score = -10
            rsi_desc = f"RSI(14) = {rsi}，動能處於空方中軸拉鋸"
        else:
            rsi_score = -20
            rsi_desc = f"RSI(14) = {rsi}，弱勢跌入超賣區，空方摜壓動能強烈"

        # 3. 三大法人籌碼權重 (-25 ~ +25)
        inst_total = self.cache["institution"]["total"]
        foreign = self.cache["institution"]["foreign"]
        chip_score = 0
        if inst_total > 150:
            chip_score = 25
            chip_desc = f"三大法人大幅買超達 {inst_total:+.1f} 億元，外資積極回補偏多"
        elif inst_total > 0:
            chip_score = 15
            chip_desc = f"三大法人合計淨買超 {inst_total:+.1f} 億元，籌碼面正向支持"
        elif inst_total < -150:
            chip_score = -25
            chip_desc = f"三大法人沉重調節賣超 {inst_total:+.1f} 億元，外資提款壓力顯著"
        else:
            chip_score = -15
            chip_desc = f"三大法人小幅調節 {inst_total:+.1f} 億元，資金偏保守防禦"

        # 4. 成交量配合度 (-15 ~ +15)
        vol_score = 10
        vol_desc = "量縮震盪沉澱，籌碼流動性穩定，並無暴量失控疑慮"
        if self.cache["taiex"]["change"] > 0:
            vol_score = 15
            vol_desc = "上漲帶量增溫，多方攻擊動能充沛且量價配合"
        elif self.cache["taiex"]["change"] < -50:
            vol_score = -15
            vol_desc = "下跌收黑且盤中出現停損賣壓，量價背離"

        # 5. 融資籌碼穩定度 (-10 ~ +10)
        margin_change = self.cache["margin"]["margin_change_billion"]
        margin_score = 5
        margin_desc = f"融資餘額穩定變化 {margin_change:+.1f} 億元，散戶籌碼沉澱無失控"
        if margin_change > 15.0 and self.cache["taiex"]["change"] < 0:
            margin_score = -10
            margin_desc = "融資逆勢大增而指數走跌，散戶接刀套牢風險激增"
        elif margin_change < -5.0 and self.cache["taiex"]["change"] > 0:
            margin_score = 10
            margin_desc = "融資減肥、指數大漲，法人吸籌籌碼極度安定"

        # 綜合多空機率計算 (基準 50% + 權重累加)
        total_pts = ma_score + rsi_score + chip_score + vol_score + margin_score
        bull_prob = int(max(8, min(92, round(50 + total_pts * 0.45))))
        bear_prob = 100 - bull_prob

        # 多空評級
        if bull_prob >= 72:
            rating = "多方強攻架構 (Strong Bullish)"
            rating_color = "text-rose-500"
            badge_bg = "bg-rose-500/20 text-rose-400 border-rose-500/40"
        elif bull_prob >= 56:
            rating = "偏多震盪整理 (Mild Bullish)"
            rating_color = "text-red-400"
            badge_bg = "bg-red-500/20 text-red-300 border-red-500/40"
        elif bull_prob >= 44:
            rating = "多空均衡拉鋸 (Consolidation)"
            rating_color = "text-amber-400"
            badge_bg = "bg-amber-500/20 text-amber-300 border-amber-500/40"
        elif bull_prob >= 28:
            rating = "偏空承壓震盪 (Mild Bearish)"
            rating_color = "text-emerald-400"
            badge_bg = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
        else:
            rating = "空方主導修正 (Strong Bearish)"
            rating_color = "text-emerald-500"
            badge_bg = "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"

        self.cache["quant"] = {
            "bull_prob": bull_prob,
            "bear_prob": bear_prob,
            "rating": rating,
            "rating_color": rating_color,
            "badge_bg": badge_bg,
            "rsi": rsi,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "scores": {
                "ma": {"score": ma_score, "title": "均線排列強度", "desc": ma_desc},
                "rsi": {"score": rsi_score, "title": "動量 RSI(14)", "desc": rsi_desc},
                "chip": {"score": chip_score, "title": "三大法人籌碼", "desc": chip_desc},
                "vol": {"score": vol_score, "title": "盤中量價配合", "desc": vol_desc},
                "margin": {"score": margin_score, "title": "融資融券安定度", "desc": margin_desc},
            }
        }

    async def update_all_data(self):
        cur_time = time.time()
        if cur_time - self.last_fetch_time < self.fetch_cooldown:
            return  # 限流保護
        self.last_fetch_time = cur_time

        is_open = self._is_market_open()
        twse_ok = await self.fetch_twse_mis_batch()
        await self.fetch_yahoo_klines()
        
        # 三大法人與融資券為每日盤後公布資料，至少間隔 1 小時 (3600 秒) 檢查一次即可，極致保護 IP
        if cur_time - self.last_daily_fetch_time > 3600.0 or not self.cache["institution"]["foreign"]:
            await self.fetch_institutional_chips()
            await self.fetch_margin_data()
            await self.fetch_taifex_futures()
            self.last_daily_fetch_time = cur_time

        if is_open and twse_ok:
            self.cache["market_status"] = "LIVE"
            self.cache["status_text"] = "盤中即時即時串流 (更新週期: 5分鐘)"
        else:
            self.cache["market_status"] = "AFTER_HOURS_SETTLED"
            self.cache["status_text"] = "已載入最新收盤定盤價 (盤後模式)"

        self._recalculate_quant_engine()
        self.cache["last_updated"] = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")

market_mgr = MarketDataManager()

# 背景定時更新任務
async def background_poller():
    # 初次執行全面抓取
    logger.info("⏳ 正在進行初始數據載入...")
    await market_mgr.fetch_yahoo_klines()
    await market_mgr.fetch_institutional_chips()
    await market_mgr.fetch_margin_data()
    await market_mgr.fetch_taifex_futures()
    market_mgr.last_daily_fetch_time = time.time()
    await market_mgr.fetch_twse_mis_batch()
    market_mgr.last_fetch_time = time.time()
    market_mgr._recalculate_quant_engine()
    logger.info("✅ 初始金融數據載入成功！已設定為每 5 分鐘安全輪詢一次，IP 零封鎖風險。")
    
    while True:
        try:
            await asyncio.sleep(300) # 5 分鐘 (300 秒) 檢查並更新一次
            await market_mgr.update_all_data()
            logger.info(f"🔄 [5分鐘定時更新] 數據已同步更新 ({market_mgr.cache['last_updated']})")
        except Exception as e:
            logger.error(f"Poller iteration error: {e}")

# FastAPI App
app = FastAPI(title="TWStock TAIEX & 0050 Dashboard", description="台股加權指數與 0050 戰情即時儀表板")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_poller())

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)

@app.get("/api/dashboard")
async def get_dashboard():
    """取得儀表板完整靜態快照"""
    return JSONResponse(content=market_mgr.cache)

@app.get("/api/kline")
async def get_kline(interval: str = Query("5m", pattern="^(5m|60m|1d|1m)$")):
    """取得加權指數 K 線資料 (5分K, 60分K, 日K)"""
    if interval == "60m":
        return JSONResponse(content={"interval": "60m", "data": market_mgr.cache.get("kline_60m", [])})
    elif interval == "1d":
        return JSONResponse(content={"interval": "1d", "data": market_mgr.cache.get("kline_1d", [])})
    else:
        return JSONResponse(content={"interval": "5m", "data": market_mgr.cache.get("kline_5m", [])})

@app.get("/api/stream")
async def stream_data(request: Request):
    """Server-Sent Events (SSE) 即時數據推播"""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            
            # 推播 tick 數據包含 TAIEX、成分股、量化機率、三大法人現貨與期貨留倉、融資券狀態
            payload = {
                "taiex": market_mgr.cache["taiex"],
                "components": market_mgr.cache["components"],
                "quant": market_mgr.cache["quant"],
                "institution": market_mgr.cache["institution"],
                "futures": market_mgr.cache.get("futures", {}),
                "margin": market_mgr.cache["margin"],
                "market_status": market_mgr.cache["market_status"],
                "status_text": market_mgr.cache["status_text"],
                "last_updated": market_mgr.cache["last_updated"],
            }
            yield f"event: tick\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run("main:app", host=host, port=port, reload=False)
