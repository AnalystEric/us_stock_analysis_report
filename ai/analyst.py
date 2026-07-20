"""質化分析生成：呼叫 LLM 撰寫各質化區塊；任一區塊失敗或無 LLM 時降級為純數據模板。"""
from __future__ import annotations

import logging

from ai import llm_client, prompts
from config import AI_FALLBACK_NOTICE
from core.models import (
    AIContent,
    CompanyProfile,
    FinancialsData,
    KeyMetrics,
    NewsBundle,
    PeerComparison,
    RatingData,
    ValuationMultiples,
)

logger = logging.getLogger(__name__)


def generate_ai_content(
    profile: CompanyProfile,
    km: KeyMetrics,
    financials: FinancialsData,
    valuation: ValuationMultiples,
    rating: RatingData,
    peers: PeerComparison,
    news: NewsBundle,
) -> AIContent:
    provider = llm_client.detect_provider()
    ai = AIContent(provider=llm_client.provider_label())

    facts = prompts.build_facts(profile, km, financials, valuation, rating, peers, news)

    # 模板 fallback（永遠先備好，確保任何情況都有內容；逐一容錯避免單一區塊出錯導致全空）
    def _safe_tpl(fn, *args, label=""):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("模板 %s 生成失敗: %s", label, exc)
            return "（本區塊資料不足，暫無法生成內容。）"

    templates = {
        "core_view": _safe_tpl(prompts.template_core_view, profile, km, financials, valuation, rating, peers, label="core_view"),
        "business_overview": _safe_tpl(prompts.template_business_overview, profile, km, financials, valuation, label="business_overview"),
        "moat": _safe_tpl(prompts.template_moat, profile, km, financials, valuation, peers, label="moat"),
        "risks": _safe_tpl(prompts.template_risks, profile, km, financials, valuation, rating, label="risks"),
        "conclusion": _safe_tpl(prompts.template_conclusion, profile, km, financials, rating, label="conclusion"),
    }

    any_ai = False
    results: dict[str, str] = {}
    for section, template_text in templates.items():
        text = None
        if provider is not None:
            prompt = prompts.build_section_prompt(section, facts)
            text = llm_client.complete(prompts.SYSTEM_PROMPT, prompt)
        if text:
            any_ai = True
            results[section] = text
        else:
            results[section] = template_text

    ai.core_view = results["core_view"]
    ai.business_overview = results["business_overview"]
    ai.moat = results["moat"]
    ai.risks = results["risks"]
    ai.conclusion = results["conclusion"]
    ai.ai_generated = any_ai
    if not any_ai:
        if provider is not None:
            # 有提供金鑰但呼叫失敗 → 顯示具體原因（例如 credit 不足 / key 無效）
            err = llm_client.last_error() or "未知原因"
            ai.notice = (f"⚠️ 已偵測到 {ai.provider} 金鑰，但 AI 呼叫失敗，已改用純數據模板。"
                         f"原因：{err}")
            ai.provider = "template（AI 呼叫失敗）"
            logger.warning("LLM 呼叫失敗，降級模板：%s", err)
        else:
            ai.notice = AI_FALLBACK_NOTICE
            ai.provider = "template"
            logger.info("未偵測到金鑰，質化區塊以純數據模板生成")
    else:
        logger.info("質化區塊由 %s 生成", ai.provider)
    return ai
