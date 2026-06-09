"""Tests for news sentiment grouping and source categorization."""

from __future__ import annotations

from datetime import datetime

from services.news_service import NewsArticle, NewsService, NewsSummary


def _article(title: str, *, source: str = "Reuters", sentiment: str = "neutral") -> NewsArticle:
    return NewsArticle(
        title=title,
        source=source,
        published_at=datetime(2026, 6, 8),
        summary="Quarterly earnings and dividend update.",
        sentiment=sentiment,
    )


def test_news_summary_groups_articles_by_sentiment():
    summary = NewsSummary(
        symbol="ABBV",
        company_name="AbbVie",
        articles=[
            _article("Dividend increase announced", sentiment="positive"),
            _article("Company outlook steady", sentiment="neutral"),
            _article("Profit decline worries investors", sentiment="negative"),
        ],
    )

    grouped = summary.articles_by_sentiment()
    assert len(grouped["positive"]) == 1
    assert len(grouped["neutral"]) == 1
    assert len(grouped["negative"]) == 1
    assert summary.neutral_count == 1


def test_classify_source_and_theme():
    service = NewsService()
    assert service.classify_source("Reuters") == "Wire / Agency"
    assert service.classify_source("Yahoo Finance") == "Financial Media"
    assert service.classify_source("Google News") == "Aggregator"
    assert service.classify_source("Local Business Journal") == "Other"

    article = _article("AbbVie raises dividend after strong earnings beat", source="CNBC")
    assert service.classify_article_theme(article) in {"dividend", "earnings", "growth"}


def test_format_summary_for_display_includes_sentiment_buckets():
    service = NewsService()
    summary = NewsSummary(
        symbol="KO",
        company_name="Coca-Cola",
        articles=[
            _article("Beat expectations", source="Bloomberg", sentiment="positive"),
            _article("Sector outlook mixed", source="MarketWatch", sentiment="neutral"),
        ],
        overall_sentiment="mixed",
        sentiment_score=0.0,
        sources_used=["Yahoo Finance", "Google News"],
        last_updated=datetime(2026, 6, 9, 10, 0),
    )

    display = service.format_summary_for_display(summary)
    assert display["neutral_count"] == 1
    assert len(display["articles_by_sentiment"]["positive"]) == 1
    assert display["sources_breakdown"][0]["category"] in {
        "Wire / Agency",
        "Financial Media",
        "Other",
    }


def test_sources_breakdown_sorts_by_count_then_name():
    service = NewsService()
    articles = [
        _article("One", source="Reuters", sentiment="positive"),
        _article("Two", source="Reuters", sentiment="neutral"),
        _article("Three", source="Bloomberg", sentiment="positive"),
    ]

    breakdown = service.sources_breakdown(articles)
    assert breakdown[0]["source"] == "Reuters"
    assert breakdown[0]["count"] == 2
    assert breakdown[0]["category"] == "Wire / Agency"
    assert breakdown[1]["source"] == "Bloomberg"
    assert breakdown[1]["count"] == 1


def test_format_article_for_display_includes_category_theme_and_date():
    service = NewsService()
    article = _article(
        "Company raises dividend after earnings beat",
        source="Seeking Alpha",
        sentiment="positive",
    )

    payload = service._format_article_for_display(article)
    assert payload["source_category"] == "Financial Media"
    assert payload["theme"] in {"dividend", "earnings", "growth"}
    assert payload["published_label"] == "Jun 08, 2026"
    assert payload["source_category_color"].startswith("#")


def test_deduplicate_articles_removes_duplicate_titles():
    service = NewsService()
    articles = [
        _article("AbbVie raises dividend outlook"),
        _article("AbbVie raises dividend outlook"),
        _article("AbbVie pipeline update"),
    ]

    unique = service._deduplicate_articles(articles)
    assert len(unique) == 2


def test_calculate_overall_sentiment_labels():
    service = NewsService()
    mixed_articles = [
        _article("Good news", sentiment="positive"),
        _article("Bad news", sentiment="negative"),
        _article("Flat news", sentiment="neutral"),
    ]
    score, label = service._calculate_overall_sentiment(mixed_articles)
    assert label == "mixed"
    assert score == 0.0

    bearish_articles = [
        _article("Downgrade", sentiment="negative"),
        _article("More downgrades", sentiment="negative"),
        _article("Steady", sentiment="neutral"),
    ]
    score, label = service._calculate_overall_sentiment(bearish_articles)
    assert label == "bearish"
    assert score < 0


def test_analyze_article_sentiment_from_keywords():
    service = NewsService()
    positive = _article("Company beat expectations and raised dividend")
    negative = _article("Profit decline and dividend cut announced")

    assert service._analyze_article_sentiment(positive) == "positive"
    assert service._analyze_article_sentiment(negative) == "negative"
