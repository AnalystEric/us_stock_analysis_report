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

    # 模板 fallback（永遠先備好，確保任何情況都有內容）
    templates = {
        "core_view": prompts.template_core_view(profile, km, valuation, rating),
        "business_overview": prompts.template_business_overview(profile),
        "moat": prompts.template_moat(profile, peers),
        "risks": prompts.template_risks(profile, valuation, rating),
        "conclusion": prompts.template_conclusion(profile, km, rating),
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
        ai.notice = AI_FALLBACK_NOTICE
        ai.provider = "template"
        logger.info("未使用 LLM，質化區塊以純數據模板生成")
    else:
        logger.info("質化區塊由 %s 生成", ai.provider)
    return ai
