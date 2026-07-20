#!/usr/bin/env python3
"""美股投資分析 PDF 報告產生器 — CLI 進入點（投行等級深度報告）。

用法：
    python main.py --input AAPL
    python main.py --input Apple --output-dir ./output
    python main.py --input NVDA --verbose

質化分析（執行摘要 / 護城河 / 風險 / 結論）在偵測到 ANTHROPIC_API_KEY 或
OPENAI_API_KEY 時由 LLM 撰寫；否則自動降級為純數據模板。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import OUTPUT_DIR
from core.report_builder import build_report_data
from core.ticker_resolver import StockNotFoundError
from report.pdf_builder import build_pdf
from utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="美股／台股投資分析 PDF 報告產生器（官方源 + yfinance + Pandas + LLM + WeasyPrint）")
    parser.add_argument("--input", "-i", required=True,
                        help="股票代號或公司名稱。美股如 AAPL / Apple；台股如 2330 / 台積電 / 6488")
    parser.add_argument("--output-dir", "-o", default=str(OUTPUT_DIR), help="PDF 輸出資料夾（預設 ./output）")
    parser.add_argument("--verbose", "-v", action="store_true", help="顯示除錯訊息")
    parser.add_argument("--keep-charts", action="store_true", help="保留 temp_images 圖檔（除錯用）")
    return parser.parse_args(argv)


def _safe_filename(name: str) -> str:
    keep = "-_. "
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return cleaned.replace(" ", "_") or "report"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    try:
        report = build_report_data(args.input)
    except StockNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("產生報告資料時發生非預期錯誤: %s", exc)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{report.profile.ticker}_{_safe_filename(report.profile.company_name)}_投資分析報告.pdf"
    output_path = output_dir / fname

    try:
        build_pdf(report, output_path, cleanup=not args.keep_charts)
    except Exception as exc:  # noqa: BLE001
        logger.exception("產生 PDF 時發生錯誤: %s", exc)
        return 3

    print(f"\n✅ 報告已產出：{output_path}")
    print(f"   質化分析來源：{report.ai.provider}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
