"""內部人與機構動向：內部人交易摘要、機構 / 內部人持股比例。"""
from __future__ import annotations

import logging

import pandas as pd

from core.models import SmartMoneyData
from data_sources.yf_client import get_ticker, safe_call, safe_info

logger = logging.getLogger(__name__)


def _insider_summary(tk) -> list[str]:
    """從 insider_purchases 摘要表整理近 6 個月內部人買賣概況。"""
    df = safe_call(lambda: tk.insider_purchases, default=None, label="insider_purchases")
    lines: list[str] = []
    if isinstance(df, pd.DataFrame) and not df.empty:
        # 該表通常為兩欄：描述文字 + 對應數值
        label_col = df.columns[0]
        value_col = df.columns[1] if len(df.columns) > 1 else None
        for _, row in df.iterrows():
            label = str(row.get(label_col, "")).strip()
            if not label or label.lower() == "nan":
                continue
            val = row.get(value_col) if value_col is not None else None
            if val is not None and not pd.isna(val):
                lines.append(f"{label}：{_fmt(val)}")
            else:
                lines.append(label)
    return lines[:6]


def _recent_transactions(tk) -> list[str]:
    """退回逐筆內部人交易（若摘要表不可用）。"""
    df = safe_call(lambda: tk.insider_transactions, default=None, label="insider_transactions")
    lines: list[str] = []
    if isinstance(df, pd.DataFrame) and not df.empty:
        cols = {c.lower(): c for c in df.columns}
        insider_c = cols.get("insider")
        text_c = cols.get("text") or cols.get("transaction")
        shares_c = cols.get("shares")
        for _, row in df.head(5).iterrows():
            parts = []
            if insider_c:
                parts.append(str(row[insider_c]))
            if text_c:
                parts.append(str(row[text_c]))
            if shares_c and not pd.isna(row[shares_c]):
                parts.append(f"{int(row[shares_c]):,} 股")
            if parts:
                lines.append("　".join(parts))
    return lines


def fetch_smart_money(ticker: str) -> SmartMoneyData:
    tk = get_ticker(ticker)
    data = SmartMoneyData()
    info = safe_info(tk)

    inst = info.get("heldPercentInstitutions")
    insider = info.get("heldPercentInsiders")
    if inst is not None and not pd.isna(inst):
        data.institutional_ownership_pct = float(inst) * 100
    if insider is not None and not pd.isna(insider):
        data.insider_ownership_pct = float(insider) * 100

    summary = _insider_summary(tk)
    if not summary:
        summary = _recent_transactions(tk)
    data.insider_summary = summary

    if (
        not data.insider_summary
        and data.institutional_ownership_pct is None
        and data.insider_ownership_pct is None
    ):
        data.warning = "查無內部人交易與機構持股資料。"

    return data


def _fmt(val) -> str:
    try:
        f = float(val)
        if abs(f) >= 1000:
            return f"{f:,.0f}"
        return f"{f:g}"
    except (TypeError, ValueError):
        return str(val)
