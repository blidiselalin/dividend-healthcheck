"""Research screen selection and CSV contract."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from services.research_screen import (
    ASSESSMENT_COLUMNS,
    SCREEN_COLUMNS,
    LlmTarget,
    candidate_packet,
    parse_screen_csv,
    request_screen_csv,
    resolve_llm_target,
    run_screen,
    screen_prompt,
    screen_user_message,
    select_screen_candidates,
    validate_screen_rows,
)


def _doc(**overrides: object) -> SimpleNamespace:
    base = {
        "symbol": "MSFT",
        "name": "Microsoft",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "industry": "Software",
        "market_cap": 3_000_000_000_000,
        "current_price": 400.0,
        "dividend_yield": 0.7,
        "annual_dividend": 3.0,
        "payout_ratio": 25.0,
        "fcf_payout_ratio": 30.0,
        "dividend_streak_years": 20,
        "dividend_cagr_5y": 10.0,
        "revenue_growth": 12.0,
        "earnings_growth": 14.0,
        "fcf_growth": 11.0,
        "price_return_5y": 80.0,
        "total_return_5y": 95.0,
        "pe_ratio": 30.0,
        "forward_pe": 28.0,
        "peg_ratio": 2.0,
        "ev_ebitda": 22.0,
        "roe": 35.0,
        "debt_to_equity": 0.4,
        "debt_to_ebitda": 0.8,
        "price_return_1y": 15.0,
        "fifty_two_week_high": 420.0,
        "source": SimpleNamespace(value="yahoo"),
        "last_updated": datetime.now(),
        "data_quality": 90,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_screen_schema_has_55_columns() -> None:
    assert len(SCREEN_COLUMNS) == 55
    assert SCREEN_COLUMNS[0] == "week_start"
    assert SCREEN_COLUMNS[-1] == "data_as_of"


def test_select_keeps_large_common_stocks_and_prefers_dividend_growth() -> None:
    rows = select_screen_candidates(
        [
            _doc(symbol="SLOW", dividend_cagr_5y=2.0),
            _doc(symbol="FAST", dividend_cagr_5y=12.0),
            _doc(symbol="TINY", market_cap=500_000_000, dividend_cagr_5y=30.0),
            _doc(symbol="FUND", name="Example ETF", dividend_cagr_5y=40.0),
        ]
    )
    assert [item.symbol for item in rows] == ["FAST", "SLOW"]


def test_user_message_contains_only_supplied_tickers() -> None:
    message = screen_user_message([_doc()])
    assert "MSFT" in message
    assert "AAPL" not in message
    assert "authoritative" in message


def test_single_ticker_input_is_compact_and_does_not_repeat_financial_fields():
    message = screen_user_message([_doc(description="x" * 1500)])
    packet = json.loads(message.split("INPUT_DATA:\n", 1)[1])
    assert packet["ticker"] == "MSFT"
    assert len(packet["business_description"]) == 600
    assert "CSV_TEMPLATE" not in message
    assert message.count('"price_usd"') == 1
    with pytest.raises(ValueError, match="exactly one"):
        screen_user_message([_doc(), _doc(symbol="OTHER")])


def test_parse_screen_csv_requires_the_schema() -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(SCREEN_COLUMNS))
    writer.writeheader()
    writer.writerow(dict.fromkeys(SCREEN_COLUMNS, "") | {"ticker": "MSFT", "rank": "1"})
    rows = parse_screen_csv(buffer.getvalue())
    assert rows[0]["ticker"] == "MSFT"
    with pytest.raises(ValueError):
        parse_screen_csv("ticker,company_name\nMSFT,Microsoft\n")


def test_local_llm_url_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIVIDENDSCOPE_LOCAL_LLM_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("DIVIDENDSCOPE_LLM_API_URL", "https://example.invalid/v1")
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "hf-test")
    target = resolve_llm_target()
    assert target is not None
    assert target.kind == "local"
    assert target.url == "http://127.0.0.1:11434/v1/chat/completions"


def _valid_row(doc=None, **overrides):
    doc = doc or _doc()
    packet = candidate_packet(doc)
    row = {column: str(packet.get(column, "")) for column in SCREEN_COLUMNS}
    today = date.today()
    row.update(
        {
            "rank": "1",
            "week_start": (today - timedelta(days=today.weekday())).isoformat(),
            "week_end": today.isoformat(),
            "portfolio_phase": "Phase 2 - Dividend Growth/Capital Gains",
            "drip_suitability": "Strong",
            "valuation_view": "Fair Value",
            "historical_growth_score": "10",
            "dividend_quality_score": "16",
            "business_growth_outlook_score": "10",
            "valuation_score": "18",
            "next_period_upside_score": "7",
            "financial_strength_score": "8",
            "sector_diversification_score": "3",
            "total_score": "72",
            "decision_label": "Good candidate",
            "source_confidence": "Medium",
            "decision_reason": "Review growth and valuation using the dated snapshot.",
            "key_risks": "Primary filing evidence and quote timestamp are unverified.",
        }
    )
    row.update(overrides)
    return row


def _csv(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(SCREEN_COLUMNS))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def test_compact_prompt_retains_the_screening_criteria_and_evidence_guards():
    prompt = screen_prompt()
    assert len(prompt) < 3000
    assert "ONE supplied US stock" in prompt
    assert "YoY growth from 5Y CAGR" in prompt
    assert "No browsing" in prompt
    assert "Do not force a recommendation" in prompt
    assert "unchanged 55-column CSV" in prompt


def test_packets_do_not_relabel_yoy_growth_and_convert_cumulative_return_to_cagr():
    packet = candidate_packet(_doc())
    assert "revenue_growth_5y_cagr_pct" not in packet
    assert "eps_growth_5y_cagr_pct" not in packet
    assert "fcf_growth_5y_cagr_pct" not in packet
    assert packet["price_cagr_5y_pct"] == pytest.approx(((1.8**0.2) - 1) * 100, abs=0.0001)
    assert packet["revenue_growth_yoy_pct"] == 12
    assert "net_debt_to_ebitda" not in packet
    assert packet["debt_to_ebitda"] == 0.8
    assert packet["confidence_limit"] == "Medium"
    assert "portfolio_shares" not in packet and "in_portfolio" not in packet


def test_yield_is_calculated_from_cash_dividend_and_price_when_source_units_conflict():
    packet = candidate_packet(_doc(dividend_yield=37, annual_dividend=1.48, current_price=400))
    assert packet["dividend_yield_pct"] == 0.37
    assert "data_warnings" in packet
    assert "calculated yield used" in screen_user_message(
        [_doc(dividend_yield=37, annual_dividend=1.48, current_price=400)]
    )


def test_zero_annual_dividend_does_not_pass_using_a_stale_positive_yield():
    assert select_screen_candidates([_doc(dividend_yield=2, annual_dividend=0)]) == []


def test_packets_leave_economically_misleading_bank_metrics_empty():
    packet = candidate_packet(_doc(sector="Financials", industry="Banks - Diversified"))
    assert "fcf_payout_ratio_pct" not in packet
    assert "ev_to_ebitda" not in packet
    assert "net_debt_to_ebitda" not in packet


def test_point_in_time_guard_and_stale_snapshot_filter():
    future = _doc(last_updated=datetime.now() + timedelta(days=1))
    with pytest.raises(ValueError, match="not available"):
        candidate_packet(future)
    assert select_screen_candidates([future]) == []
    stale = _doc(last_updated=datetime.now() - timedelta(days=8))
    assert candidate_packet(stale)["confidence_limit"] == "Low"
    assert select_screen_candidates([stale]) == []


def test_held_candidates_are_included_without_favoring_high_yield():
    selected = select_screen_candidates(
        [_doc(symbol="NEW", dividend_cagr_5y=12), _doc(symbol="HELD", dividend_cagr_5y=3)],
        limit=1,
        held_symbols={"HELD"},
    )
    assert [doc.symbol for doc in selected] == ["HELD"]
    assert select_screen_candidates([_doc(dividend_yield=0.5)])


@pytest.mark.parametrize(
    "overrides",
    [
        {"exchange": "LSE"},
        {"current_price": 1},
        {"currency": "EUR"},
        {"name": "Example Preferred Shares"},
        {"name": "Example Acquisition Corp"},
        {"market_cap": float("nan")},
        {"dividend_yield": 0},
        {"last_updated": None},
    ],
)
def test_unreliable_or_out_of_universe_candidates_are_excluded(overrides):
    assert select_screen_candidates([_doc(**overrides)]) == []


def test_valid_csv_keeps_55_columns_and_is_grounded_in_supplied_snapshots():
    row = _valid_row()
    rows = parse_screen_csv(_csv([row]))
    validate_screen_rows(rows, [_doc()])
    assert len(rows[0]) == 55
    assert rows[0] == row


@pytest.mark.parametrize(
    "overrides",
    [
        {"ticker": "INVENTED"},
        {"price_usd": "999"},
        {"forward_eps_growth_pct": "15"},
        {"eps_growth_5y_cagr_pct": "14"},
        {"total_score": "99"},
        {"valuation_score": "26"},
        {"source_confidence": "High"},
        {"primary_source": "https://invented.example/filing"},
        {"data_as_of": "2099-01-01"},
        {"week_end": "2099-01-01"},
        {"decision_label": "Buy immediately"},
    ],
)
def test_unsupported_model_output_is_rejected(overrides):
    with pytest.raises(ValueError):
        validate_screen_rows([_valid_row(**overrides)], [_doc()])


def test_malformed_duplicate_and_oversized_csv_is_rejected():
    row = _valid_row()
    with pytest.raises(ValueError):
        parse_screen_csv(_csv([row, row]))
    with pytest.raises(ValueError):
        parse_screen_csv(_csv([row]).replace("MSFT", "MSFT,EXTRA", 1))
    with pytest.raises(ValueError):
        parse_screen_csv(_csv([dict(row, ticker=f"T{i}") for i in range(11)]))


@pytest.mark.parametrize("model", ["openrouter/free", "nvidia/nemotron-3.5-super-vl:free"])
def test_request_uses_the_prompt_and_validates_the_response(monkeypatch, model):
    import requests

    captured = {}
    row = _valid_row(
        decision_reason='Review growth, coverage and "valuation".',
        sector_diversification_score="0",
        total_score="69",
    )
    assessment = {column: row[column] for column in ASSESSMENT_COLUMNS}

    def post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [{"message": {"content": json.dumps({"rows": [assessment]})}}]
            },
        )

    monkeypatch.setattr(requests, "post", post)
    raw = request_screen_csv(
        [_doc()],
        target=LlmTarget(
            "https://openrouter.ai/api/v1/chat/completions", model, "test-key", "cloud"
        ),
    )
    assert parse_screen_csv(raw) == [row]
    messages = captured["json"]["messages"]
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["json"]["model"] == model
    assert captured["json"]["max_tokens"] == 1200
    assert captured["json"]["reasoning"] == {"enabled": False, "exclude": True}
    assert captured["json"]["provider"] == {"require_parameters": True}
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert messages[0]["content"] == screen_prompt()
    schema = captured["json"]["response_format"]["json_schema"]["schema"]
    assert tuple(schema["properties"]["rows"]["items"]["properties"]) == ASSESSMENT_COLUMNS
    assert schema["properties"]["rows"]["maxItems"] == 1
    assert "ONE supplied US stock" in messages[0]["content"]
    assert "INPUT_DATA" in messages[1]["content"]
    assert "portfolio_shares" not in messages[1]["content"]


@pytest.mark.parametrize("rows", [None, {}, [{"ticker": "MSFT"}]])
def test_structured_response_rejects_malformed_rows(monkeypatch, rows):
    import requests

    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": json.dumps({"rows": rows})}}]},
        ),
    )
    with pytest.raises(ValueError, match="assessment string fields"):
        request_screen_csv(
            [_doc()],
            target=LlmTarget("https://openrouter.ai/api/v1/chat/completions", "free", "", "cloud"),
        )


def test_multiple_tickers_use_separate_calls_and_rank_the_top_ten(monkeypatch):
    calls = []
    progress = []
    documents = [_doc(symbol=f"S{i:02d}") for i in range(12)]

    def review(candidates, **kwargs):
        calls.append([doc.symbol for doc in candidates])
        doc = candidates[0]
        score = int(doc.symbol[1:])
        return _csv([_valid_row(doc, valuation_score=str(score), total_score=str(54 + score))])

    monkeypatch.setattr("services.research_screen.request_screen_csv", review)
    rows, failures = run_screen(
        documents + [documents[0]],
        target=LlmTarget("http://local/v1", "test", "", "local"),
        on_progress=lambda done, total, symbol: progress.append((done, total)),
    )
    assert calls == [[doc.symbol] for doc in documents]
    assert not failures
    assert [row["ticker"] for row in rows] == [f"S{i:02d}" for i in range(11, 1, -1)]
    assert [row["rank"] for row in rows] == [str(i) for i in range(1, 11)]
    assert progress[-1] == (12, 12)
    assert all(len(row) == 55 for row in rows)


def test_failed_ticker_does_not_discard_other_reviews(monkeypatch):
    calls = []

    def review(candidates, **kwargs):
        doc = candidates[0]
        calls.append(doc.symbol)
        if doc.symbol == "BAD":
            raise ValueError("invalid model response")
        return _csv([_valid_row(doc)])

    monkeypatch.setattr("services.research_screen.request_screen_csv", review)
    rows, failures = run_screen(
        [_doc(symbol=symbol) for symbol in ("OK", "BAD", "GOOD")],
        target=LlmTarget("http://local/v1", "test", "", "local"),
    )
    assert calls == ["OK", "BAD", "GOOD"]
    assert [row["ticker"] for row in rows] == ["GOOD", "OK"]
    assert failures == {"BAD": "Invalid model response"}


@pytest.mark.parametrize("status", [401, 403, 429])
def test_auth_and_rate_limits_stop_remaining_calls(monkeypatch, status):
    import requests

    calls = []
    response = requests.Response()
    response.status_code = status

    def review(candidates, **kwargs):
        calls.append(candidates[0].symbol)
        raise requests.HTTPError(response=response)

    monkeypatch.setattr("services.research_screen.request_screen_csv", review)
    rows, failures = run_screen(
        [_doc(symbol=symbol) for symbol in ("A", "B", "C")],
        target=LlmTarget("http://local/v1", "test", "", "local"),
    )
    assert calls == ["A"]
    assert rows == [] and set(failures) == {"A", "B", "C"}
