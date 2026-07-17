# 美股投資分析 PDF 報告產生器（投行等級深度報告）

輸入**美股代號**或**公司名稱**，自動查詢公開資料（以 [`yfinance`](https://github.com/ranaroussi/yfinance) 為核心），
經 Pandas 分析、專業圖表、（選用）LLM 質化分析與 **WeasyPrint (HTML→PDF)** 排版，
產出一份**如同 sell-side 研究報告**的中文（中英夾雜）PDF。

> ⚠️ 所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。

---

## 架構（模組化）

```
us-stock-report/
├── main.py                  CLI 進入點
├── app.py                   Streamlit 網頁介面
├── bootstrap_libs.py        macOS 上為 WeasyPrint 設定原生庫路徑（程式內自動）
├── config.py                全域設定（HTTP / retry / DPI / LLM 金鑰偵測）
│
├── data_sources/            【Data ETL】yfinance 資料獲取
│   ├── yf_client.py           yfinance 封裝（瀏覽器 UA、快取、容錯）
│   ├── profile_fetcher.py     基本資訊
│   ├── price_fetcher.py       股價 / 均線 / 52 週
│   ├── financials_fetcher.py  近 8 季營收/YoY/毛利率/FCF/EPS Beat-Miss
│   ├── segments_fetcher.py    年度營收結構
│   ├── valuation_fetcher.py   P/E、P/S、EV/Sales、EV/FCF、PEG…
│   ├── rating_fetcher.py      華爾街評等 / 目標價（+ 網站備援）
│   ├── options_fetcher.py     Put/Call Ratio
│   ├── ownership_fetcher.py   內部人 / 機構持股
│   └── peers_fetcher.py       同業比較
│
├── analytics/metrics.py     【資料處理】YoY、CAGR、FCF 利潤率、情境目標價、關鍵數據彙整
│
├── ai/                      【AI 分析（LLM）】
│   ├── llm_client.py          供應商無關（Anthropic / OpenAI 自動偵測）
│   ├── prompts.py             Prompt 組裝 + 純數據模板 fallback
│   └── analyst.py             生成 核心觀點 / 護城河 / 風險 / 結論
│
├── viz/                     【視覺化】Matplotlib 商務風格圖表（白底、300 DPI）
│   ├── style.py               配色與主題
│   ├── fonts.py               中文字型解析
│   └── charts.py              7 種圖表（含 mplfinance K 線）
│
├── report/                  【排版】WeasyPrint HTML→PDF
│   ├── templates/report.html.j2
│   ├── styles.css             商務 CSS（Zebra striping、頁尾免責聲明/頁碼）
│   └── pdf_builder.py         Jinja2 渲染 + 圖表內嵌 + 產出 + 清理暫存
│
├── news/                    多來源新聞（yfinance → StockAnalysis → Google News RSS）
├── utils/                   HTTP retry、logging
└── scripts/setup_fonts.py   中文字型下載備援
```

---

## 報告章節與圖表

| 區塊 | 內容 | 圖表 |
|------|------|------|
| 封面 | 公司、代號、產業、市值、股價、共識 | — |
| 執行摘要與關鍵數據 | LLM 核心觀點 + 關鍵數據一覽表 | — |
| 第一章 業務概述與護城河 | 業務模式、護城河分析 | 圖 1 營收結構 |
| 第二章 深度財務視覺化 | 季度財務明細表 | 圖 2 營收+YoY 雙軸、圖 3 毛利率/FCF 利潤率、圖 4 EPS Beat/Miss |
| 第三章 估值與籌碼 | 估值倍數表、選擇權情緒、內部人/機構 | 圖 5 K 線+均線+成交量、P/E 趨勢 |
| 第四章 同業比較 | 市值/成長/毛利/淨利/EV·Sales/Fwd P/E 對比表 | 同業毛利/淨利長條圖 |
| 第五章 風險與結論 | LLM 風險提示、情境目標價、結論 | — |
| 附錄 | 近期新聞摘要（多來源） | — |

每頁頁尾固定顯示投資免責聲明與頁碼；表格採交替底色（Zebra striping）。

---

## 安裝

需要 Python 3.10+。

```bash
cd us-stock-report
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### WeasyPrint 系統相依（重要）

WeasyPrint 需要原生庫（pango / cairo / gobject）：

- **macOS**：`brew install pango gdk-pixbuf libffi`
  （程式已自動把 `/opt/homebrew/lib` 加入動態庫搜尋路徑，**不需手動 export**。）
- **Debian/Ubuntu**：`sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev`
- **Windows**：建議使用 MSYS2 安裝 GTK，或參考 WeasyPrint 官方文件。

### 中文字型

程式會依序尋找：`fonts/` 內使用者字型 → 系統中文字型（macOS/Linux/Windows）→ 下載 Noto Sans CJK TC。
macOS / 多數 Linux 已內建可用字型，通常**免手動準備**。
如需指定，把 `NotoSansTC-Regular.otf`（或微軟正黑體 `msjh.ttf`）放入 `fonts/` 即可。

### LLM 質化分析（選用）

設定環境變數即可啟用 AI 撰寫的深度質化分析；未設定則自動降級為純數據模板。

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # 優先
# 或
export OPENAI_API_KEY=sk-...
```

（可用 `.env` 檔，見 `.env.example`。）

---

## 使用方式

### CLI

```bash
python main.py --input AAPL
python main.py --input Apple --output-dir ./output
python main.py --input NVDA --verbose
```

產出於 `output/{代號}_{公司名}_投資分析報告.pdf`。

### 網頁介面（Streamlit）

```bash
streamlit run app.py
```

輸入代號 → 線上預覽關鍵數據與圖表 → 一鍵下載 PDF。

---

## 開發原則與容錯

- 只使用**合法、公開、免登入、免 API Key** 的資料（主要為 yfinance）；LLM 為選用增強。
- 對外請求皆帶瀏覽器 User-Agent（yfinance 另以 curl_cffi 模擬 Chrome 指紋），並具指數退避 retry。
- **全面容錯**：任一資料源 / LLM / 圖表 / 區塊失敗，只讓對應部分留白並記錄，程式不崩潰。
- 新聞為多來源 fallback 架構；圖表暫存於 `temp_images/`，PDF 產出後自動清理。

## 已知限制

- yfinance 季度財報通常僅約 5 季，較舊季度的 YoY 可能無法計算。
- 歷史 P/E 為近似（歷史股價 ÷ 目前 TTM EPS），僅供位階參考。
- yfinance 無穩定的「部門別」營收，營收結構圖以年度營收規模呈現。
- Yahoo 部分端點可能回 429；程式具備援與重試。

---

## 授權與免責

僅供教育與個人研究用途。資料來自第三方公開來源。
**所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。**
