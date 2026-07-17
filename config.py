"""全域設定與常數。"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv 為選用，缺少時不影響主流程
    pass

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR = BASE_DIR / "fonts"
TEMP_IMAGES_DIR = BASE_DIR / "temp_images"  # 圖表暫存，PDF 產出後清理

for _d in (CACHE_DIR, OUTPUT_DIR, FONTS_DIR):
    _d.mkdir(exist_ok=True)

# --- HTTP ---
HTTP_TIMEOUT_SECONDS = 20
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# --- Retry ---
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.5

# --- 資料範圍 ---
PRICE_PERIOD = "1y"
PRICE_PERIOD_VALUATION = "3y"
QUARTERS_LOOKBACK = 8          # 深度財務視覺化用近 8 季
NEWS_MAX_ITEMS = 12
NEWS_PER_PROVIDER = 8
PEERS_MAX = 4                  # 同業比較最多列幾家（含本公司外 3-4 家）

# --- 圖表 ---
CHART_DPI = 300                # 高解析度確保 PDF 放大不失真

# --- LLM ---
# 供應商自動偵測：優先 Anthropic，其次 OpenAI；皆無則 fallback 至純數據模板。
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
# 模型可用環境變數覆寫
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o").strip()
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1500"))

DISCLAIMER_TEXT = (
    "所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。"
)

# 無 LLM 時，質化區塊使用的預設提示語
AI_FALLBACK_NOTICE = (
    "（本區塊未啟用 AI 分析：未偵測到 LLM API Key，以下為依據公開數據自動生成的摘要。"
    "如需 AI 撰寫的深度質化分析，請設定 ANTHROPIC_API_KEY 或 OPENAI_API_KEY 後重新產出。）"
)
