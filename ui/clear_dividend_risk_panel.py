"""
Clear Dividend Risk UI — holding evidence (PR 2) and portfolio summary (PR 3).

Educational / evidence-only — no buy, sell, or hold recommendations.
Assessment is computed from already-loaded library data (no external API calls).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from services.clear_dividend_risk import (
    METHODOLOGY_VERSION,
    ConcentrationLevel,
    ConfidenceLevel,
    DividendRiskAlert,
    HoldingDividendRiskAssessment,
    PortfolioDividendIncomeRisk,
    PortfolioHoldingIncomeInput,
    RiskLevel,
    RiskSignal,
    assess_holding_dividend_risk,
    assess_holdings_dividend_risk,
    assess_portfolio_dividend_income_risk,
    build_high_value_dividend_risk_alerts,
    evidence_from_stock_data,
    evidence_from_stock_document,
    load_risk_evidence_batch,
    with_yield_channel,
)

DISCLAIMER = (
    "Dividend sustainability is an educational research indicator based on "
    "available coverage and dividend-history evidence. It is not financial advice "
    "and does not recommend buying, selling, or holding any security."
)

_CONFIDENCE_LABELS = {
    ConfidenceLevel.HIGH: "High",
    ConfidenceLevel.MEDIUM: "Medium",
    ConfidenceLevel.LOW: "Low",
}


def confidence_label(level: ConfidenceLevel) -> str:
    return _CONFIDENCE_LABELS.get(level, level.value.title())


def format_as_of(value: date | None) -> str:
    if value is None:
        return "Not available"
    return value.strftime("%B %d, %Y")


def assess_holding_for_ui(
    *,
    symbol: str,
    stock: Any | None = None,
    vector_doc: Any | None = None,
    yield_channel: Any | None = None,
    today: date | None = None,
) -> HoldingDividendRiskAssessment:
    """Build evidence from preloaded document/stock/yield channel and assess once."""
    symbol_u = (symbol or getattr(stock, "symbol", "") or "").upper()
    if vector_doc is not None:
        evidence = evidence_from_stock_document(vector_doc)
    elif stock is not None:
        evidence = evidence_from_stock_data(stock)
    else:
        from services.clear_dividend_risk import DividendRiskEvidence, SecurityType

        evidence = DividendRiskEvidence(
            symbol=symbol_u or "UNKNOWN",
            security_type=SecurityType.UNKNOWN,
        )
    if evidence.symbol and evidence.symbol != symbol_u and symbol_u:
        # Keep caller symbol authoritative for UI keys.
        from dataclasses import replace

        evidence = replace(evidence, symbol=symbol_u)
    if yield_channel is None:
        import streamlit as st

        cached = st.session_state.get("portfolio_yield_cache") or {}
        if isinstance(cached, dict):
            yield_channel = cached.get(symbol_u)
    return assess_holding_dividend_risk(
        with_yield_channel(evidence, yield_channel),
        today=today,
    )


def primary_signal_messages(
    assessment: HoldingDividendRiskAssessment,
    *,
    limit: int = 3,
) -> tuple[str, ...]:
    actionable = [
        signal.message
        for signal in assessment.risk_signals
        if signal.severity in {"high", "monitor"}
    ]
    if actionable:
        return tuple(actionable[:limit])
    if assessment.summary:
        return (assessment.summary,)
    return ()


def evidence_table_rows(
    assessment: HoldingDividendRiskAssessment,
) -> list[tuple[str, str]]:
    """Rows for the Review evidence expander (What / Evidence)."""
    rows: list[tuple[str, str]] = [
        ("Dividend sustainability", assessment.risk_label),
        ("Data confidence", confidence_label(assessment.confidence)),
        ("As of", format_as_of(assessment.data_as_of)),
        ("Methodology", f"Clear Dividend Risk {assessment.methodology_version}"),
    ]
    if assessment.source_names:
        rows.append(("Sources", ", ".join(assessment.source_names)))

    for signal in assessment.risk_signals:
        detail = signal.message
        if signal.threshold_description:
            detail = f"{detail} (threshold: {signal.threshold_description})"
        if signal.observed_value is not None:
            detail = f"{detail} · observed={signal.observed_value}"
        rows.append((f"Signal · {signal.code}", detail))

    observed = assessment.observed_values or {}
    for key in (
        "fcf_payout_ratio",
        "earnings_payout_ratio",
        "dividend_coverage",
        "dividend_yield",
        "yield_channel_zone",
        "yield_channel_percentile",
        "yield_channel_current",
        "yield_channel_median",
        "debt_to_ebitda",
        "debt_to_equity",
        "interest_coverage",
        "dividend_cagr_3y",
        "annual_dividend",
        "affo_payout_ratio",
        "ffo_payout_ratio",
        "security_type",
        "hard_monitor_signal_count",
    ):
        value = observed.get(key)
        if value is None or value == []:
            continue
        rows.append((f"Observed · {key}", str(value)))

    if assessment.missing_fields:
        rows.append(("Missing data", ", ".join(assessment.missing_fields)))

    return rows


def resolve_estimated_annual_income(
    symbol: str,
    *,
    estimated_annual_income: float | None = None,
    portfolio_rows: Sequence[Any] | None = None,
) -> float | None:
    if estimated_annual_income is not None:
        return float(estimated_annual_income)
    if not portfolio_rows:
        return None
    symbol_u = symbol.upper()
    for row in portfolio_rows:
        ticker = str(getattr(row, "ticker", "") or "").upper()
        if ticker != symbol_u:
            continue
        income = getattr(row, "annual_income", None)
        if income is None:
            return None
        return float(income)
    return None


def format_income(amount: float | None) -> str:
    if amount is None:
        return "Not available"
    return f"${amount:,.0f}"


def _render_evidence_expander(
    assessment: HoldingDividendRiskAssessment,
    *,
    key_suffix: str,
) -> None:
    import pandas as pd
    import streamlit as st

    rows = evidence_table_rows(assessment)
    with st.expander("Review evidence", expanded=False):
        st.caption(
            "Evidence used for this sustainability assessment. "
            "Verify sources and dates before drawing conclusions."
        )
        if not rows:
            st.info("No evidence rows available.")
            return
        frame = pd.DataFrame(rows, columns=["What", "Evidence"])
        st.dataframe(
            frame,
            width="stretch",
            hide_index=True,
            column_config={
                "What": st.column_config.TextColumn(width="medium"),
                "Evidence": st.column_config.TextColumn(width="large"),
            },
            key=f"clear_dividend_risk_evidence_{key_suffix}",
        )


def render_holding_clear_dividend_risk(
    symbol: str,
    *,
    stock: Any | None = None,
    vector_doc: Any | None = None,
    estimated_annual_income: float | None = None,
    assessment: HoldingDividendRiskAssessment | None = None,
    show_income: bool = True,
) -> HoldingDividendRiskAssessment:
    """
    Render dividend sustainability status, confidence, signals, and evidence.

    Returns the assessment so callers can reuse it in the same render pass.
    """
    import streamlit as st

    from ui.design_system import (
        render_disclaimer_banner,
        render_health_panel,
        render_metric_grid,
        render_status_badge,
    )

    symbol_u = (symbol or "").upper()
    result = assessment or assess_holding_for_ui(
        symbol=symbol_u,
        stock=stock,
        vector_doc=vector_doc,
    )

    portfolio_rows = st.session_state.get("portfolio_details_rows")
    income = resolve_estimated_annual_income(
        symbol_u,
        estimated_annual_income=estimated_annual_income,
        portfolio_rows=portfolio_rows if isinstance(portfolio_rows, list) else None,
    )

    reasons = primary_signal_messages(result)
    render_health_panel(
        result.risk_label,
        reasons,
        title="Dividend sustainability",
    )

    badge_cols = st.columns([1, 1, 2])
    with badge_cols[0]:
        st.caption("Status")
        render_status_badge(result.risk_label)
    with badge_cols[1]:
        st.caption("Data confidence")
        render_status_badge(confidence_label(result.confidence))
    with badge_cols[2]:
        st.caption(f"As of: {format_as_of(result.data_as_of)}")
        st.caption(f"Methodology: Clear Dividend Risk {result.methodology_version}")

    metric_items: list[tuple[str, str, str] | tuple[str, str, str, bool]] = []
    if show_income:
        metric_items.append(
            (
                "Est. annual income (holding)",
                format_income(income),
                "From portfolio shares × dividend — not risk-adjusted",
                True,
            )
        )
    observed = result.observed_values or {}
    metric_items.extend(
        [
            (
                "FCF payout",
                _fmt_pct(observed.get("fcf_payout_ratio")),
                f"High ≥ {result.threshold_descriptions.get('fcf_payout_high_min_pct', '90%')}",
                False,
            ),
            (
                "Earnings payout",
                _fmt_pct(observed.get("earnings_payout_ratio")),
                f"High ≥ {result.threshold_descriptions.get('earnings_payout_high_min_pct', '90%')}",
                False,
            ),
            (
                "Yield channel",
                str(observed.get("yield_channel_zone") or "—"),
                (
                    f"Weiss zone · pctl {_fmt_pct(observed.get('yield_channel_percentile'), suffix='')}"
                    if observed.get("yield_channel_percentile") is not None
                    else "Weiss historical yield bands"
                ),
                False,
            ),
            (
                "Channel yield",
                _fmt_pct(observed.get("yield_channel_current") or observed.get("dividend_yield")),
                (
                    f"Median {_fmt_pct(observed.get('yield_channel_median'))}"
                    if observed.get("yield_channel_median") is not None
                    else "Current vs history"
                ),
                False,
            ),
            (
                "Debt / EBITDA",
                _fmt_ratio(observed.get("debt_to_ebitda")),
                "Soft context — not automatic High",
                False,
            ),
            (
                "Interest coverage",
                _fmt_ratio(observed.get("interest_coverage")),
                "Soft context — not automatic High",
                False,
            ),
        ]
    )
    if reasons:
        metric_items.append(
            (
                "Main signal",
                reasons[0][:80] + ("…" if len(reasons[0]) > 80 else ""),
                "Why this holding is flagged",
                False,
            )
        )
    if metric_items:
        render_metric_grid(metric_items)

    if len(reasons) > 1:
        st.markdown("**Why this is flagged**")
        for message in reasons:
            st.markdown(f"- {message}")

    _render_evidence_expander(result, key_suffix=symbol_u or "unknown")
    render_disclaimer_banner(DISCLAIMER)
    return result


_SEVERITY_ORDER = {
    RiskLevel.HIGH_OBSERVED_RISK: 0,
    RiskLevel.MONITOR: 1,
    RiskLevel.INSUFFICIENT_DATA: 2,
    RiskLevel.SPECIAL_ANALYSIS_REQUIRED: 3,
    RiskLevel.LOWER_OBSERVED_RISK: 4,
}

_CONCENTRATION_LABELS = {
    ConcentrationLevel.NONE: "Diversified",
    ConcentrationLevel.MONITOR: "Monitor concentration",
    ConcentrationLevel.HIGH: "High concentration",
}


@dataclass(frozen=True)
class PortfolioClearRiskTableRow:
    symbol: str
    company: str
    estimated_annual_income: float
    income_share_pct: float
    sustainability_status: str
    confidence: str
    main_signal: str
    yield_channel_zone: str
    fcf_payout_pct: float | None
    earnings_payout_pct: float | None
    dividend_yield_pct: float | None
    debt_to_ebitda: float | None
    data_as_of: str
    action: str
    assessment: HoldingDividendRiskAssessment


@dataclass(frozen=True)
class PortfolioClearRiskView:
    portfolio: PortfolioDividendIncomeRisk
    table_rows: tuple[PortfolioClearRiskTableRow, ...]
    assessments: dict[str, HoldingDividendRiskAssessment]
    alerts: tuple[DividendRiskAlert, ...] = ()


def concentration_label(level: ConcentrationLevel) -> str:
    return _CONCENTRATION_LABELS.get(level, level.value)


def _fmt_pct(value: Any, *, suffix: str = "%") -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _fmt_ratio(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}x"
    except (TypeError, ValueError):
        return "—"


def _observed_float(assessment: HoldingDividendRiskAssessment, key: str) -> float | None:
    value = (assessment.observed_values or {}).get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _lookup_cached(mapping: Mapping[str, Any] | None, symbol: str) -> Any | None:
    if not mapping:
        return None
    return mapping.get(symbol) or mapping.get(symbol.upper()) or mapping.get(symbol.lower())


def build_portfolio_clear_dividend_risk(
    rows: Sequence[Any],
    *,
    vector_docs: Mapping[str, Any] | None = None,
    stock_by_symbol: Mapping[str, Any] | None = None,
    yield_channels: Mapping[str, Any] | None = None,
    today: date | None = None,
) -> PortfolioClearRiskView:
    """
    Batch-assess holdings from preloaded caches (one pass, no I/O).

    Prefer vector documents for dividend-history cut detection.
    Yield channels (Weiss) refine absolute yield into value vs trap context.
    """
    company_by_symbol: dict[str, str] = {}
    symbols: list[str] = []
    for row in rows:
        symbol = str(getattr(row, "ticker", "") or "").upper()
        if not symbol:
            continue
        if getattr(row, "shares", None) is not None and float(row.shares) <= 0:
            continue
        company_by_symbol[symbol] = str(getattr(row, "company", None) or symbol).strip()
        symbols.append(symbol)

    # Prefer batch-loaded market documents — never reconstruct evidence from UI rows.
    cached_docs = {
        symbol: doc
        for symbol in symbols
        if (doc := _lookup_cached(vector_docs, symbol)) is not None
    }
    evidence_by_symbol = load_risk_evidence_batch(symbols, documents=cached_docs)
    for symbol in symbols:
        if symbol in evidence_by_symbol:
            continue
        stock = _lookup_cached(stock_by_symbol, symbol)
        if stock is not None:
            evidence_by_symbol[symbol] = evidence_from_stock_data(stock)
        else:
            from services.clear_dividend_risk import DividendRiskEvidence, SecurityType

            evidence_by_symbol[symbol] = DividendRiskEvidence(
                symbol=symbol,
                security_type=SecurityType.UNKNOWN,
                sector=next(
                    (
                        getattr(row, "sector", None)
                        for row in rows
                        if str(getattr(row, "ticker", "")).upper() == symbol
                    ),
                    None,
                ),
            )

    assessments = assess_holdings_dividend_risk(
        evidence_by_symbol,
        today=today,
        yield_channels=yield_channels,
    )
    inputs: list[PortfolioHoldingIncomeInput] = []
    for row in rows:
        symbol = str(getattr(row, "ticker", "") or "").upper()
        if symbol not in assessments:
            continue
        inputs.append(
            PortfolioHoldingIncomeInput(
                symbol=symbol,
                estimated_annual_income=float(getattr(row, "annual_income", 0.0) or 0.0),
                sector=getattr(row, "sector", None),
                assessment=assessments[symbol],
            )
        )

    portfolio = assess_portfolio_dividend_income_risk(inputs)
    total = portfolio.total_estimated_annual_income or 0.0
    table: list[PortfolioClearRiskTableRow] = []
    for item in inputs:
        assessment = item.assessment
        assert assessment is not None
        income = max(0.0, item.estimated_annual_income)
        share = (income / total * 100.0) if total > 0 else 0.0
        signals = primary_signal_messages(assessment, limit=1)
        zone = str((assessment.observed_values or {}).get("yield_channel_zone") or "—")
        table.append(
            PortfolioClearRiskTableRow(
                symbol=item.symbol,
                company=company_by_symbol.get(item.symbol, item.symbol),
                estimated_annual_income=income,
                income_share_pct=round(share, 1),
                sustainability_status=assessment.risk_label,
                confidence=confidence_label(assessment.confidence),
                main_signal=signals[0] if signals else assessment.summary,
                yield_channel_zone=zone,
                fcf_payout_pct=_observed_float(assessment, "fcf_payout_ratio"),
                earnings_payout_pct=_observed_float(assessment, "earnings_payout_ratio"),
                dividend_yield_pct=_observed_float(assessment, "yield_channel_current")
                or _observed_float(assessment, "dividend_yield"),
                debt_to_ebitda=_observed_float(assessment, "debt_to_ebitda"),
                data_as_of=format_as_of(assessment.data_as_of),
                action="Review evidence",
                assessment=assessment,
            )
        )

    table.sort(
        key=lambda row: (
            _SEVERITY_ORDER.get(row.assessment.risk_level, 9),
            -row.estimated_annual_income,
            row.symbol,
        )
    )
    alerts = build_high_value_dividend_risk_alerts(portfolio)
    return PortfolioClearRiskView(
        portfolio=portfolio,
        table_rows=tuple(table),
        assessments=assessments,
        alerts=alerts,
    )


def portfolio_income_metric_items(
    portfolio: PortfolioDividendIncomeRisk,
) -> list[tuple[str, str, str] | tuple[str, str, str, bool]]:
    """Headline metrics for the Dividend income risk strip (keep high-level)."""
    items: list[tuple[str, str, str] | tuple[str, str, str, bool]] = [
        (
            "Estimated annual income",
            format_income(portfolio.total_estimated_annual_income),
            "Sum of holding estimates — not risk-adjusted",
            True,
        ),
        (
            "Income to watch",
            format_income(portfolio.income_elevated_risk),
            f"{portfolio.income_elevated_share_pct:.0f}% on Monitor or High",
            True,
        ),
        (
            "Holdings to watch",
            (
                f"{portfolio.elevated_holdings_count} · "
                f"{portfolio.high_risk_holdings_count} high / "
                f"{portfolio.monitor_holdings_count} monitor"
            ),
            "Coverage or cut signals — review evidence",
            True,
        ),
    ]
    if portfolio.largest_income_contributor is not None:
        symbol, amount, share = portfolio.largest_income_contributor
        items.append(
            (
                "Largest income name",
                f"{symbol} · {share:.0f}%",
                f"{format_income(amount)} · {concentration_label(portfolio.company_concentration)}",
                False,
            )
        )
    return items


def elevated_holdings_for_display(
    table_rows: Sequence[PortfolioClearRiskTableRow],
    *,
    limit: int = 12,
) -> list[PortfolioClearRiskTableRow]:
    """High + Monitor holdings, already severity-sorted in the portfolio table."""
    elevated = [
        row
        for row in table_rows
        if row.assessment.risk_level in {RiskLevel.HIGH_OBSERVED_RISK, RiskLevel.MONITOR}
    ]
    return elevated[:limit]


def _status_chip_kind(level: RiskLevel) -> str:
    if level is RiskLevel.HIGH_OBSERVED_RISK:
        return "risky"
    if level is RiskLevel.MONITOR:
        return "watch"
    return "healthy"


def _watch_chip_items(
    table_rows: Sequence[PortfolioClearRiskTableRow],
) -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    for row in elevated_holdings_for_display(table_rows):
        signal = row.main_signal
        if len(signal) > 42:
            signal = signal[:41] + "…"
        detail = f"{row.sustainability_status} · {format_income(row.estimated_annual_income)}"
        if signal:
            detail = f"{detail} · {signal}"
        items.append((row.symbol, detail, _status_chip_kind(row.assessment.risk_level)))
    return items


def _render_watch_holding_buttons(
    items: list[tuple[str, str, str]],
    *,
    nav_tickers: list[str],
    key_prefix: str = "cdr_watch",
) -> None:
    """Clickable High/Monitor holdings — HTML chips alone are not interactive."""
    import streamlit as st

    from ui.portfolio_home import set_holding_selection

    if not items:
        return
    cols = st.columns(min(len(items), 4))
    for index, (symbol, detail, _kind) in enumerate(items):
        with cols[index % len(cols)]:
            label = f"{symbol} · {detail}"
            if len(label) > 72:
                label = label[:71] + "…"
            if st.button(
                label,
                key=f"{key_prefix}_{symbol}",
                use_container_width=True,
                help="Open holding evidence",
            ):
                set_holding_selection(symbol, nav_tickers=nav_tickers)


def _render_high_value_alerts(alerts: Sequence[DividendRiskAlert]) -> None:
    import streamlit as st

    from ui.design_system import render_status_badge

    if not alerts:
        return

    st.markdown("**Alerts worth a look**")
    st.caption(
        "Educational flags only — not buy, sell, or hold advice. "
        "Concentration alerts need yield above 6%."
    )
    for alert in alerts:
        if alert.code in {
            "ALERT_COMPANY_INCOME_CONCENTRATION",
            "ALERT_SECTOR_INCOME_CONCENTRATION",
        }:
            badge = "High concentration"
        elif alert.severity == "high":
            badge = "High observed risk"
        else:
            badge = "Monitor"
        cols = st.columns([1, 4])
        with cols[0]:
            render_status_badge(badge)
        with cols[1]:
            st.markdown(f"**{alert.title}**")
            st.caption(alert.message)


def portfolio_table_records(
    table_rows: Sequence[PortfolioClearRiskTableRow],
) -> list[dict[str, Any]]:
    return [
        {
            "Holding": row.symbol,
            "Company": row.company,
            "Est. annual income": row.estimated_annual_income,
            "Share of income %": row.income_share_pct,
            "Sustainability": row.sustainability_status,
            "Confidence": row.confidence,
            "Yield zone": row.yield_channel_zone,
            "FCF payout %": row.fcf_payout_pct,
            "Earnings payout %": row.earnings_payout_pct,
            "Yield %": row.dividend_yield_pct,
            "Debt/EBITDA": row.debt_to_ebitda,
            "Main signal": row.main_signal,
            "Data date": row.data_as_of,
            "Action": row.action,
        }
        for row in table_rows
    ]


def _render_concentration_summary(
    portfolio: PortfolioDividendIncomeRisk,
    *,
    zone_summary: str,
) -> None:
    import streamlit as st

    from services.clear_dividend_risk import CONCENTRATION_ALERT_MIN_YIELD_PCT
    from ui.design_system import render_status_badge

    company_detail = "—"
    if portfolio.largest_income_contributor is not None:
        symbol, _amount, share = portfolio.largest_income_contributor
        company_detail = f"{symbol} · {share:.0f}% of income"

    sector_detail = "—"
    if portfolio.largest_sector_income is not None:
        sector, _amount, share = portfolio.largest_sector_income
        sector_detail = f"{sector} · {share:.0f}% of income"

    cols = st.columns(3)
    with cols[0]:
        st.caption("Company concentration")
        render_status_badge(concentration_label(portfolio.company_concentration))
        st.caption(company_detail)
        st.caption(f"High alert if yield > {CONCENTRATION_ALERT_MIN_YIELD_PCT:.0f}%")
    with cols[1]:
        st.caption("Sector concentration")
        render_status_badge(concentration_label(portfolio.sector_concentration))
        st.caption(sector_detail)
        st.caption(f"High alert if yield > {CONCENTRATION_ALERT_MIN_YIELD_PCT:.0f}%")
    with cols[2]:
        st.caption("Yield-channel mix")
        st.caption(zone_summary if zone_summary != "—" else "Load yield charts for Weiss zones")
        st.caption("High yield vs history ≈ value unless coverage is stressed")


def render_portfolio_clear_dividend_risk(
    rows: Sequence[Any],
    *,
    table_key: str | None = None,
    vector_docs: Mapping[str, Any] | None = None,
    stock_by_symbol: Mapping[str, Any] | None = None,
    yield_channels: Mapping[str, Any] | None = None,
) -> PortfolioClearRiskView | None:
    """Home / Dividend Income portfolio Clear Dividend Risk summary."""
    from collections import Counter

    import pandas as pd
    import streamlit as st

    from ui.design_system import (
        close_table_container,
        render_disclaimer_banner,
        render_home_panel,
        render_html,
        render_section_header,
        wrap_table_container,
    )
    from ui.session_keys import HOME_CLEAR_DIVIDEND_RISK_TABLE_KEY

    if table_key is None:
        table_key = HOME_CLEAR_DIVIDEND_RISK_TABLE_KEY

    if not rows:
        return None

    if vector_docs is None:
        cached_docs = st.session_state.get("portfolio_vector_docs") or {}
        vector_docs = cached_docs if isinstance(cached_docs, dict) else {}
    if stock_by_symbol is None:
        cached_stocks = st.session_state.get("portfolio_stock_cache") or {}
        stock_by_symbol = cached_stocks if isinstance(cached_stocks, dict) else {}
    if yield_channels is None:
        cached_channels = st.session_state.get("portfolio_yield_cache") or {}
        yield_channels = cached_channels if isinstance(cached_channels, dict) else {}

    view = build_portfolio_clear_dividend_risk(
        rows,
        vector_docs=vector_docs,
        stock_by_symbol=stock_by_symbol,
        yield_channels=yield_channels,
    )
    portfolio = view.portfolio
    nav_tickers = [row.symbol for row in view.table_rows]

    render_home_panel(
        "Dividend income risk",
        "Quick view of which holdings need a closer look. "
        "Coverage and cuts drive risk; yield-channel zones add valuation context. "
        f"Research only · methodology {METHODOLOGY_VERSION}.",
        portfolio_income_metric_items(portfolio),
    )

    watch_items = _watch_chip_items(view.table_rows)
    render_html('<div class="ds-watch-panel">')
    render_section_header(
        "Holdings to watch",
        "Monitor and High observed risk — click a holding to open evidence.",
    )
    render_html(
        '<div class="ds-watch-legend">'
        '<span><i class="ds-watch-dot ds-watch-dot-risky"></i> High</span>'
        '<span><i class="ds-watch-dot ds-watch-dot-watch"></i> Monitor</span>'
        '<span><i class="ds-watch-dot ds-watch-dot-healthy"></i> Lower risk stays off this list</span>'
        "</div>"
    )
    if watch_items:
        _render_watch_holding_buttons(watch_items, nav_tickers=nav_tickers)
    else:
        st.caption("Nothing on Monitor or High right now — coverage looks calm across holdings.")
    render_html("</div>")

    zone_counts = Counter(
        row.yield_channel_zone
        for row in view.table_rows
        if row.yield_channel_zone and row.yield_channel_zone != "—"
    )
    zone_summary = (
        " · ".join(f"{zone} {count}" for zone, count in zone_counts.most_common())
        if zone_counts
        else "—"
    )
    _render_concentration_summary(portfolio, zone_summary=zone_summary)
    _render_high_value_alerts(view.alerts)

    if not view.table_rows:
        st.info("No open holdings with dividend-risk assessments yet.")
        render_disclaimer_banner(DISCLAIMER)
        return view

    with st.expander("All holdings · income & evidence", expanded=bool(watch_items)):
        st.caption("Select a row to open holding evidence. Sorted by risk severity.")
        wrap_table_container()
        frame = pd.DataFrame(portfolio_table_records(view.table_rows))
        selection = st.dataframe(
            frame,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=table_key,
            column_config={
                "Holding": st.column_config.TextColumn(width="small"),
                "Company": st.column_config.TextColumn(width="medium"),
                "Est. annual income": st.column_config.NumberColumn(format="$%.0f"),
                "Share of income %": st.column_config.NumberColumn(format="%.1f%%"),
                "Sustainability": st.column_config.TextColumn(width="medium"),
                "Confidence": st.column_config.TextColumn(width="small"),
                "Yield zone": st.column_config.TextColumn(width="small"),
                "FCF payout %": st.column_config.NumberColumn(format="%.1f%%"),
                "Earnings payout %": st.column_config.NumberColumn(format="%.1f%%"),
                "Yield %": st.column_config.NumberColumn(format="%.1f%%"),
                "Debt/EBITDA": st.column_config.NumberColumn(format="%.1fx"),
                "Main signal": st.column_config.TextColumn(width="large"),
                "Data date": st.column_config.TextColumn(width="medium"),
                "Action": st.column_config.TextColumn(width="small"),
            },
        )
        close_table_container()

        selected_rows = getattr(getattr(selection, "selection", None), "rows", None) or []
        if selected_rows:
            index = int(selected_rows[0])
            if 0 <= index < len(view.table_rows):
                from ui.portfolio_home import set_holding_selection

                set_holding_selection(
                    view.table_rows[index].symbol,
                    nav_tickers=nav_tickers,
                )

    render_disclaimer_banner(DISCLAIMER)
    return view


# Re-export enums for tests / callers that only import the panel module.
__all__ = [
    "DISCLAIMER",
    "ConcentrationLevel",
    "ConfidenceLevel",
    "DividendRiskAlert",
    "HoldingDividendRiskAssessment",
    "METHODOLOGY_VERSION",
    "PortfolioClearRiskTableRow",
    "PortfolioClearRiskView",
    "RiskLevel",
    "RiskSignal",
    "assess_holding_for_ui",
    "build_portfolio_clear_dividend_risk",
    "concentration_label",
    "confidence_label",
    "elevated_holdings_for_display",
    "evidence_table_rows",
    "format_as_of",
    "format_income",
    "portfolio_income_metric_items",
    "portfolio_table_records",
    "primary_signal_messages",
    "render_holding_clear_dividend_risk",
    "render_portfolio_clear_dividend_risk",
    "resolve_estimated_annual_income",
]
