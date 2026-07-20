"""供應商無關的 LLM 呼叫層。

自動偵測環境變數：優先 Anthropic（官方 anthropic SDK），其次 OpenAI（官方 openai SDK）。
兩者皆無 API Key、SDK 未安裝、或呼叫失敗時，complete() 回傳 None，
由上層（analyst）自動降級為純數據模板，程式不會崩潰。
"""
from __future__ import annotations

import logging

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    LLM_MAX_TOKENS,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)

# 執行時可由前端注入的金鑰（優先於環境變數）。僅存於記憶體，不寫檔、不記錄。
_RUNTIME: dict[str, str | None] = {"anthropic_key": None, "openai_key": None}

# 最近一次 LLM 呼叫的錯誤訊息（供前端顯示失敗原因，例如 credit 不足 / key 無效）
_LAST_ERROR: dict[str, str] = {"msg": ""}


def last_error() -> str:
    return _LAST_ERROR["msg"]


def _friendly_error(exc: Exception) -> str:
    """把常見錯誤轉成好懂的中文提示。"""
    text = str(exc)
    low = text.lower()
    if "credit balance is too low" in low or "billing" in low:
        return "帳戶 credit 不足：請到 console.anthropic.com（或 platform.openai.com）Billing 購買額度。"
    if "authentication" in low or "invalid x-api-key" in low or "401" in low or "invalid_api_key" in low:
        return "API Key 無效：請確認金鑰是否正確、未過期。"
    if "rate limit" in low or "429" in low:
        return "觸發速率限制（429）：請稍後再試。"
    if "model" in low and ("not found" in low or "does not exist" in low or "404" in low):
        return "模型名稱無法使用：請確認帳戶是否有該模型權限。"
    return text[:200]


def set_runtime_keys(anthropic_key: str = "", openai_key: str = "") -> None:
    """由前端（如 Streamlit）注入使用者自帶金鑰；空字串代表清除。"""
    _RUNTIME["anthropic_key"] = (anthropic_key or "").strip() or None
    _RUNTIME["openai_key"] = (openai_key or "").strip() or None


def _anthropic_key() -> str:
    return _RUNTIME["anthropic_key"] or ANTHROPIC_API_KEY


def _openai_key() -> str:
    return _RUNTIME["openai_key"] or OPENAI_API_KEY


def credentials_fingerprint() -> str:
    """回傳供快取鍵使用的識別字串（不含金鑰明文）。"""
    import hashlib

    p = detect_provider() or "template"
    key = _anthropic_key() if p == "anthropic" else (_openai_key() if p == "openai" else "")
    digest = hashlib.sha256(key.encode()).hexdigest()[:8] if key else "none"
    return f"{p}:{digest}"


def detect_provider() -> str | None:
    """回傳 'anthropic' / 'openai' / None（考慮執行時注入的金鑰）。"""
    if _anthropic_key():
        return "anthropic"
    if _openai_key():
        return "openai"
    return None


def provider_label() -> str:
    p = detect_provider()
    if p == "anthropic":
        return f"Anthropic ({ANTHROPIC_MODEL})"
    if p == "openai":
        return f"OpenAI ({OPENAI_MODEL})"
    return "template"


def _complete_anthropic(system: str, prompt: str) -> str | None:
    try:
        import anthropic
    except ImportError:
        _LAST_ERROR["msg"] = "未安裝 anthropic 套件。"
        logger.warning("未安裝 anthropic 套件，略過 Anthropic 呼叫")
        return None
    try:
        client = anthropic.Anthropic(api_key=_anthropic_key())
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            _LAST_ERROR["msg"] = "Anthropic 以安全理由拒絕回應（refusal）。"
            logger.warning("Anthropic 回應 refusal，改用模板")
            return None
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        text = "\n".join(p for p in parts if p).strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 - LLM 失敗不可中斷報告
        _LAST_ERROR["msg"] = _friendly_error(exc)
        logger.warning("Anthropic 呼叫失敗（降級模板）: %s", exc)
        return None


def _complete_openai(system: str, prompt: str) -> str | None:
    try:
        import openai
    except ImportError:
        _LAST_ERROR["msg"] = "未安裝 openai 套件。"
        logger.warning("未安裝 openai 套件，略過 OpenAI 呼叫")
        return None
    try:
        client = openai.OpenAI(api_key=_openai_key())
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR["msg"] = _friendly_error(exc)
        logger.warning("OpenAI 呼叫失敗（降級模板）: %s", exc)
        return None


def complete(system: str, prompt: str) -> str | None:
    """呼叫偵測到的供應商；失敗回傳 None。"""
    _LAST_ERROR["msg"] = ""
    provider = detect_provider()
    if provider == "anthropic":
        return _complete_anthropic(system, prompt)
    if provider == "openai":
        return _complete_openai(system, prompt)
    return None
