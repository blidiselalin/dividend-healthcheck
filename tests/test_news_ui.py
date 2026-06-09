"""Tests for news sentiment UI rendering helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.news_service import NewsArticle, NewsService, NewsSummary
from ui.components import UIComponents


def _display_article(**overrides) -> dict:
    base = {
        "title": "Dividend increase announced",
        "source": "Reuters",
        "sentiment": "positive",
        "theme": "dividend",
        "source_category": "Wire / Agency",
        "source_category_color": "#1565c0",
        "published_label": "Jun 08, 2026",
        "summary": "Quarterly payout raised.",
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_streamlit(monkeypatch):
    mock_st = MagicMock()
    mock_st.spinner = _null_context
    mock_st.columns.return_value = [MagicMock() for _ in range(5)]
    mock_st.tabs.return_value = [MagicMock(), MagicMock(), MagicMock()]
    monkeypatch.setattr("ui.components.st", mock_st)
    return mock_st


@contextmanager
def _null_context(*args, **kwargs):
    yield MagicMock()


def test_render_news_article_card_emits_sentiment_html(mock_streamlit):
    captured: list[str] = []
    mock_streamlit.markdown.side_effect = lambda html, **kwargs: captured.append(html)

    UIComponents._render_news_article_card(_display_article())
    assert captured
    html = captured[0]
    assert "Dividend increase announced" in html
    assert "#4caf50" in html
    assert "Wire / Agency" in html
    assert "Dividend" in html


def test_render_news_sentiment_group_shows_empty_caption(mock_streamlit):
    container = MagicMock()
    container.__enter__ = MagicMock(return_value=None)
    container.__exit__ = MagicMock(return_value=False)

    UIComponents._render_news_sentiment_group(
        container,
        [],
        empty_text="No clearly positive headlines in this window.",
    )
    mock_streamlit.caption.assert_called_once_with(
        "No clearly positive headlines in this window."
    )


def test_display_news_summary_renders_sentiment_tabs(mock_streamlit):
    summary = NewsSummary(
        symbol="ABBV",
        company_name="AbbVie",
        articles=[
            NewsArticle(
                title="Beat expectations",
                source="Reuters",
                published_at=datetime(2026, 6, 8),
                summary="Strong quarter.",
                sentiment="positive",
            ),
            NewsArticle(
                title="Sector outlook mixed",
                source="MarketWatch",
                published_at=datetime(2026, 6, 7),
                summary="Macro headwinds.",
                sentiment="neutral",
            ),
        ],
        overall_sentiment="mixed",
        sentiment_score=0.0,
        sources_used=["Reuters"],
        last_updated=datetime(2026, 6, 9, 10, 0),
    )

    with patch("ui.components.NEWS_AVAILABLE", True), patch.object(
        NewsService, "fetch_news_summary", return_value=summary
    ):
        assert UIComponents.display_news_summary("ABBV", days=7) is True

    mock_streamlit.tabs.assert_called_once()
    tab_labels = mock_streamlit.tabs.call_args[0][0]
    assert tab_labels[0].startswith("🟢 Positive")
    assert tab_labels[1].startswith("⚪ Neutral")
    assert tab_labels[2].startswith("🔴 Negative")


def test_display_news_summary_returns_false_when_no_articles(mock_streamlit):
    empty = NewsSummary(symbol="XYZ", company_name="Example")

    with patch("ui.components.NEWS_AVAILABLE", True), patch.object(
        NewsService, "fetch_news_summary", return_value=empty
    ):
        assert UIComponents.display_news_summary("XYZ") is False

    mock_streamlit.caption.assert_called()
