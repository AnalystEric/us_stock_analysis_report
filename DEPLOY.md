# 部署指南（讓其他人上網使用）

本 app 依賴 WeasyPrint 的原生系統庫與中文字型，**不能只推 `.py`**。以下兩條路都已備好對應檔案。

---

## ⚠️ 上線前務必決定兩件事

1. **LLM 金鑰 = 你的錢。** 若把 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` 設在伺服器，
   每位使用者跑報告都消耗你的額度。三種選擇：
   - 不設金鑰 → 只跑「純數據模板」（零成本、仍完整）。
   - 讓使用者自帶金鑰（可再幫你在介面加輸入框）。
   - 設金鑰 + 加密碼保護 / 限流。
2. **Yahoo 可能封鎖雲端 IP。** yfinance 在雲端（尤其免費層）比本機更常被 429 / 擋掉。
   已有 retry + 快取緩解；若嚴重需自備代理或改資料源。

---

## 路線 A：Streamlit Community Cloud（最簡單、免費）

1. 把整個專案推到 **GitHub**（`.gitignore` 已排除 `.venv/`、`output/`、`.env`、
   `.streamlit/secrets.toml`，金鑰不會外洩）。
2. 前往 <https://share.streamlit.io> → 用 GitHub 登入 → **New app** → 選你的 repo、
   分支、主檔 `app.py`。
3. 平台會自動：讀 `requirements.txt`（Python 套件）+ `packages.txt`（apt 系統庫，
   含 `fonts-noto-cjk` 中文字型）。
4. （選用）App → **Settings → Secrets** 貼上金鑰（格式見 `.streamlit/secrets.toml.example`）；
   平台會同時以環境變數注入，程式即可讀到。
5. Deploy，取得公開網址分享即可。

> 免費層有記憶體/休眠限制；產 PDF 尖峰可能較慢，但可運作。

---

## 路線 B：Docker →（Render / Railway / Zeabur / Fly.io / 自架 VPS）

專案內已含 **`Dockerfile`**（裝好 pango/cairo + `fonts-noto-cjk`）與 `.dockerignore`。

本機測試：
```bash
docker build -t us-stock-report .
docker run -p 8501:8501 -e ANTHROPIC_API_KEY=sk-ant-... us-stock-report
# 開 http://localhost:8501
```

部署到 PaaS（擇一）：
- **Render / Railway / Zeabur**：連 GitHub repo → 選「Docker」→ 在平台的
  Environment / Variables 設 `ANTHROPIC_API_KEY`（或不設）→ 部署。平台以 `$PORT` 指定埠，
  Dockerfile 已處理。
- **自架 VPS**：`git pull` → `docker build` → `docker run`（可搭配 Nginx + HTTPS）。

> Docker 路線最穩定、環境可控，也最不受免費層限制；推薦要「給多人穩定使用」時採用。

---

## 需不需要 GitHub？

- 路線 A、以及 Render/Railway/Zeabur 的 Git 連動：**需要**推到 GitHub。
- 自架 VPS 用 Docker：可用 GitHub，也可直接把程式碼複製上主機、本地 build。

---

## 常見結構檢查

- ✅ `requirements.txt`（Python 套件，含 pymupdf / weasyprint / streamlit…）
- ✅ `packages.txt`（Streamlit Cloud 用的 apt 系統庫 + 中文字型）
- ✅ `Dockerfile` / `.dockerignore`（容器部署）
- ✅ `.streamlit/config.toml`（伺服器設定）
- ✅ `.streamlit/secrets.toml.example`（金鑰範本；真檔已被 gitignore）
- ✅ `.gitignore`（排除金鑰、venv、輸出、字型二進位）
