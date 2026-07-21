"""
Financial News Service for Dividend Stock Analysis.

Fetches and summarizes news from top public financial sources:
- Yahoo Finance (primary - most reliable)
- Google News RSS
- MarketWatch RSS
- Seeking Alpha RSS

Provides sentiment analysis and key highlights for investment decisions.
"""

from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_NEWS_DAYS = 7
MAX_ARTICLES = 15
REQUEST_TIMEOUT = 10

# Try to import dependencies
try:
    import yfinance as yf

    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    import feedparser

    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


@dataclass
class NewsArticle:
    """Represents a financial news article."""

    title: str
    source: str
    published_at: datetime | None = None
    url: str | None = None
    summary: str | None = None
    sentiment: str | None = None  # "positive", "negative", "neutral"
    relevance: float = 1.0  # 0-1 relevance score

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "url": self.url,
            "summary": self.summary,
            "sentiment": self.sentiment,
            "relevance": self.relevance,
        }


@dataclass
class NewsSummary:
    """Summary of news for a stock."""

    symbol: str
    company_name: str
    articles: list[NewsArticle] = field(default_factory=list)
    overall_sentiment: str = "neutral"  # "bullish", "bearish", "neutral", "mixed"
    sentiment_score: float = 0.0  # -1 to 1
    key_themes: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    last_updated: datetime | None = None
    sources_used: list[str] = field(default_factory=list)

    @property
    def article_count(self) -> int:
        return len(self.articles)

    @property
    def positive_count(self) -> int:
        return sum(1 for a in self.articles if a.sentiment == "positive")

    @property
    def negative_count(self) -> int:
        return sum(1 for a in self.articles if a.sentiment == "negative")

    @property
    def neutral_count(self) -> int:
        return sum(1 for a in self.articles if a.sentiment == "neutral")

    def articles_by_sentiment(self) -> dict[str, list[NewsArticle]]:
        grouped: dict[str, list[NewsArticle]] = {
            "positive": [],
            "neutral": [],
            "negative": [],
        }
        for article in self.articles:
            bucket = article.sentiment or "neutral"
            if bucket not in grouped:
                bucket = "neutral"
            grouped[bucket].append(article)
        return grouped


class NewsService:
    """
    Service for fetching and analyzing financial news.

    Aggregates news from multiple public sources and provides
    summarized insights for dividend stock investors.
    """

    SOURCE_CATEGORY_RULES: ClassVar[dict[str, tuple[str, ...]]] = {
        "Wire / Agency": (
            "reuters",
            "associated press",
            "ap news",
            "bloomberg",
            "afp",
            "dow jones",
        ),
        "Financial Media": (
            "yahoo finance",
            "cnbc",
            "marketwatch",
            "seeking alpha",
            "barron",
            "wall street journal",
            "wsj",
            "financial times",
            "benzinga",
            "motley fool",
            "investor's business daily",
            "thestreet",
            "fool.com",
            "investopedia",
        ),
        "Aggregator": ("google news", "msn", "news.google"),
        "Research / Ratings": ("zacks", "tipranks", "morningstar", "simply wall st"),
    }

    SOURCE_CATEGORY_COLORS: ClassVar[dict[str, str]] = {
        "Wire / Agency": "#1565c0",
        "Financial Media": "#2e7d32",
        "Aggregator": "#6a1b9a",
        "Research / Ratings": "#ef6c00",
        "Other": "#546e7a",
    }

    # Keywords indicating positive news for dividend investors
    POSITIVE_KEYWORDS: ClassVar[list[str]] = [
        "dividend increase",
        "dividend hike",
        "raised dividend",
        "dividend growth",
        "beats estimates",
        "exceeds expectations",
        "strong earnings",
        "profit growth",
        "record revenue",
        "upgraded",
        "buy rating",
        "outperform",
        "raises guidance",
        "increases payout",
        "higher dividend",
        "dividend aristocrat",
        "dividend king",
        "cash flow increase",
        "shareholder return",
        "buyback",
        "repurchase",
        "beat expectations",
        "exceeded",
        "raises outlook",
        "positive momentum",
    ]

    # Keywords indicating negative news for dividend investors
    NEGATIVE_KEYWORDS: ClassVar[list[str]] = [
        "dividend cut",
        "dividend reduction",
        "suspends dividend",
        "eliminated dividend",
        "misses estimates",
        "below expectations",
        "weak earnings",
        "profit decline",
        "revenue miss",
        "downgraded",
        "sell rating",
        "underperform",
        "lowers guidance",
        "reduced payout",
        "lower dividend",
        "dividend risk",
        "payout concern",
        "cash flow decline",
        "debt concern",
        "credit downgrade",
        "restructuring",
        "layoffs",
        "missed expectations",
        "disappointing",
        "negative outlook",
    ]

    # Keywords for key financial themes
    THEME_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "earnings": ["earnings", "eps", "profit", "revenue", "quarter", "fiscal"],
        "dividend": ["dividend", "payout", "yield", "distribution", "income"],
        "growth": ["growth", "expansion", "increase", "rising", "gains"],
        "valuation": ["valuation", "price target", "rating", "upgrade", "downgrade"],
        "management": ["ceo", "management", "executive", "leadership", "appointment"],
        "market": ["market", "sector", "industry", "competition", "outlook"],
    }

    def __init__(self, days: int = DEFAULT_NEWS_DAYS) -> None:
        """Initialize news service."""
        self.days = days
        self._session = None

        if REQUESTS_AVAILABLE:
            self._session = requests.Session()
            self._session.headers.update(
                {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )

    def fetch_news_summary(
        self,
        symbol: str,
        days: int | None = None,
        max_articles: int = MAX_ARTICLES,
    ) -> NewsSummary:
        """
        Fetch and summarize news for a stock.

        Args:
            symbol: Stock ticker symbol
            days: Number of days to look back (default: 7)
            max_articles: Maximum articles to fetch

        Returns:
            NewsSummary with articles, sentiment, and highlights
        """
        if days is None:
            days = self.days

        # Get company name
        company_name = symbol
        try:
            if YFINANCE_AVAILABLE:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                company_name = info.get("shortName") or info.get("longName") or symbol
        except Exception:  # noqa: S110
            pass

        # Fetch from all sources
        all_articles: list[NewsArticle] = []
        sources_used: list[str] = []

        # Yahoo Finance (primary)
        if YFINANCE_AVAILABLE:
            yf_articles = self._fetch_yahoo_finance(symbol, days, max_articles)
            if yf_articles:
                all_articles.extend(yf_articles)
                sources_used.append("Yahoo Finance")

        # Google News RSS
        if FEEDPARSER_AVAILABLE:
            google_articles = self._fetch_google_news(symbol, company_name, days, max_articles // 3)
            if google_articles:
                all_articles.extend(google_articles)
                if "Google News" not in sources_used:
                    sources_used.append("Google News")

        # Deduplicate by title similarity
        unique_articles = self._deduplicate_articles(all_articles)

        # Analyze sentiment for each article
        for article in unique_articles:
            article.sentiment = self._analyze_article_sentiment(article)

        # Sort by date (most recent first)
        unique_articles.sort(key=lambda a: a.published_at or datetime.min, reverse=True)

        # Limit to max articles
        unique_articles = unique_articles[:max_articles]

        # Calculate overall sentiment
        sentiment_score, overall_sentiment = self._calculate_overall_sentiment(unique_articles)

        # Extract key themes and highlights
        key_themes = self._extract_themes(unique_articles)
        highlights, risks = self._extract_highlights_and_risks(unique_articles)

        return NewsSummary(
            symbol=symbol,
            company_name=company_name,
            articles=unique_articles,
            overall_sentiment=overall_sentiment,
            sentiment_score=sentiment_score,
            key_themes=key_themes,
            highlights=highlights,
            risks=risks,
            last_updated=datetime.now(),
            sources_used=sources_used,
        )

    def _fetch_yahoo_finance(self, symbol: str, days: int, max_results: int) -> list[NewsArticle]:  # noqa: C901
        """Fetch news from Yahoo Finance."""
        articles = []

        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news or []
            cutoff = datetime.utcnow() - timedelta(days=days)

            for item in news[: max_results * 2]:  # Fetch extra for filtering
                if not item or not isinstance(item, dict):
                    continue

                # Handle new yfinance content format
                content = item.get("content", {})
                if content:
                    title = content.get("title", "")
                    summary = content.get("summary", content.get("description", ""))
                    pub_date_str = content.get("pubDate", "")
                    url = item.get("clickThroughUrl", {}).get("url", "") or item.get(
                        "canonicalUrl", {}
                    ).get("url", "")
                    provider = content.get("provider", {}).get("displayName", "") or item.get(
                        "provider", {}
                    ).get("displayName", "Yahoo Finance")

                    pub = None
                    if pub_date_str:
                        with contextlib.suppress(ValueError, TypeError):
                            pub = datetime.fromisoformat(
                                pub_date_str.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                else:
                    # Old format fallback
                    title = item.get("title", "")
                    summary = item.get("summary", "")
                    url = item.get("link", "")
                    provider = item.get("publisher", "Yahoo Finance")

                    pub = None
                    if item.get("providerPublishTime"):
                        with contextlib.suppress(ValueError, TypeError):
                            pub = datetime.utcfromtimestamp(item["providerPublishTime"])

                # Filter by date
                if pub and pub < cutoff:
                    continue

                if not title:
                    continue

                articles.append(
                    NewsArticle(
                        title=self._clean_text(title),
                        source=provider or "Yahoo Finance",
                        published_at=pub,
                        url=url,
                        summary=self._clean_text(summary) if summary else None,
                    )
                )

                if len(articles) >= max_results:
                    break

        except requests.exceptions.RequestException as e:
            logger.debug(f"Yahoo Finance news fetch error for {symbol}: {e}")

        return articles

    def _fetch_google_news(
        self, symbol: str, company_name: str, days: int, max_results: int
    ) -> list[NewsArticle]:
        """Fetch news from Google News RSS."""
        articles = []

        try:
            # Search for company name + stock
            query = f"{company_name} stock {symbol}"
            encoded_query = quote_plus(query)
            rss_url = (
                f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            )

            feed = feedparser.parse(rss_url)
            cutoff = datetime.utcnow() - timedelta(days=days)

            for entry in feed.entries[: max_results * 2]:
                try:
                    pub = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub = datetime(*entry.published_parsed[:6])

                    if pub and pub < cutoff:
                        continue

                    title = entry.get("title", "")
                    # Google News titles often include source at end
                    if " - " in title:
                        title, source = title.rsplit(" - ", 1)
                    else:
                        source = "Google News"

                    link = entry.get("link", "")
                    summary = entry.get("summary", "")

                    # Clean HTML from summary
                    summary = re.sub(r"<[^>]+>", "", summary)

                    if title:
                        articles.append(
                            NewsArticle(
                                title=self._clean_text(title),
                                source=source.strip(),
                                published_at=pub,
                                url=link,
                                summary=self._clean_text(summary) if summary else None,
                            )
                        )

                    if len(articles) >= max_results:
                        break

                except requests.exceptions.RequestException:  # noqa: S112
                    continue

        except Exception as e:
            logger.debug(f"Google News fetch error for {symbol}: {e}")

        return articles

    def _clean_text(self, text: str) -> str:
        """Clean text by removing extra whitespace and special characters."""
        if not text:
            return ""

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Remove source attributions
        text = re.sub(r"\s*-\s*(Reuters|AP|Bloomberg|CNBC|MarketWatch).*$", "", text, flags=re.I)

        # Normalize whitespace
        text = " ".join(text.split())

        return text.strip()

    def _deduplicate_articles(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        """Remove duplicate articles based on title similarity."""
        seen_titles = set()
        unique = []

        for article in articles:
            # Normalize title for comparison
            normalized = article.title.lower().strip()
            # Remove common prefixes
            normalized = re.sub(r"^(breaking|update|exclusive):\s*", "", normalized)

            # Simple dedup using first 50 chars
            key = normalized[:50]

            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(article)

        return unique

    def _analyze_article_sentiment(self, article: NewsArticle) -> str:
        """Analyze sentiment of a single article."""
        text = f"{article.title} {article.summary or ''}".lower()

        positive_score = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
        negative_score = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)

        if positive_score > negative_score:
            return "positive"
        elif negative_score > positive_score:
            return "negative"
        else:
            return "neutral"

    def _calculate_overall_sentiment(self, articles: list[NewsArticle]) -> tuple[float, str]:
        """Calculate overall sentiment from articles."""
        if not articles:
            return 0.0, "neutral"

        positive = sum(1 for a in articles if a.sentiment == "positive")
        negative = sum(1 for a in articles if a.sentiment == "negative")
        total = len(articles)

        # Score from -1 (all negative) to 1 (all positive)
        score = (positive - negative) / total

        # Determine label
        if positive > 0 and negative > 0:
            if abs(score) < 0.2:
                sentiment = "mixed"
            elif score > 0:
                sentiment = "bullish"
            else:
                sentiment = "bearish"
        elif positive > negative:
            sentiment = "bullish"
        elif negative > positive:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        return round(score, 2), sentiment

    def _extract_themes(self, articles: list[NewsArticle]) -> list[str]:
        """Extract key themes from articles."""
        theme_counts: dict[str, int] = {}

        for article in articles:
            text = f"{article.title} {article.summary or ''}".lower()

            for theme, keywords in self.THEME_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    theme_counts[theme] = theme_counts.get(theme, 0) + 1

        # Return top themes
        sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
        return [theme for theme, _ in sorted_themes[:4]]

    def _extract_highlights_and_risks(
        self, articles: list[NewsArticle]
    ) -> tuple[list[str], list[str]]:
        """Extract key highlights and risks from articles."""
        highlights = []
        risks = []

        for article in articles[:10]:  # Focus on most recent
            title = article.title

            # Check for positive highlights
            for kw in self.POSITIVE_KEYWORDS:
                if kw in title.lower():
                    highlights.append(title)
                    break

            # Check for risks
            for kw in self.NEGATIVE_KEYWORDS:
                if kw in title.lower():
                    risks.append(title)
                    break

        # Deduplicate and limit
        return list(dict.fromkeys(highlights))[:3], list(dict.fromkeys(risks))[:3]

    def classify_source(self, source: str) -> str:
        """Map a publisher name to a display category."""
        normalized = (source or "").strip().lower()
        for category, needles in self.SOURCE_CATEGORY_RULES.items():
            if any(needle in normalized for needle in needles):
                return category
        return "Other"

    def classify_article_theme(self, article: NewsArticle) -> str:
        """Pick the strongest content theme for one headline."""
        text = f"{article.title} {article.summary or ''}".lower()
        best_theme = "general"
        best_score = 0
        for theme, keywords in self.THEME_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_theme = theme
        return best_theme

    def sources_breakdown(self, articles: list[NewsArticle]) -> list[dict[str, Any]]:
        """Count articles by publisher and source category."""
        counts: dict[tuple[str, str], int] = {}
        for article in articles:
            source = article.source or "Unknown"
            category = self.classify_source(source)
            key = (source, category)
            counts[key] = counts.get(key, 0) + 1
        rows = [
            {"source": source, "category": category, "count": count}
            for (source, category), count in counts.items()
        ]
        rows.sort(key=lambda row: (-int(str(row["count"])), str(row["source"]).lower()))
        return rows

    def _format_article_for_display(self, article: NewsArticle) -> dict[str, Any]:
        category = self.classify_source(article.source or "")
        payload = article.to_dict()
        payload["source_category"] = category
        payload["source_category_color"] = self.SOURCE_CATEGORY_COLORS.get(
            category, self.SOURCE_CATEGORY_COLORS["Other"]
        )
        payload["theme"] = self.classify_article_theme(article)
        if article.published_at:
            payload["published_label"] = article.published_at.strftime("%b %d, %Y")
        else:
            payload["published_label"] = ""
        return payload

    def format_summary_for_display(self, summary: NewsSummary) -> dict[str, Any]:
        """Format news summary for UI display."""
        sentiment_emoji = {
            "bullish": "📈",
            "bearish": "📉",
            "neutral": "-",
            "mixed": "🔄",
        }

        sentiment_color = {
            "bullish": "#4caf50",
            "bearish": "#f44336",
            "neutral": "#9e9e9e",
            "mixed": "#ff9800",
        }

        return {
            "symbol": summary.symbol,
            "company_name": summary.company_name,
            "article_count": summary.article_count,
            "sentiment": summary.overall_sentiment,
            "sentiment_emoji": sentiment_emoji.get(summary.overall_sentiment, "-"),
            "sentiment_color": sentiment_color.get(summary.overall_sentiment, "#9e9e9e"),
            "sentiment_score": summary.sentiment_score,
            "positive_count": summary.positive_count,
            "neutral_count": summary.neutral_count,
            "negative_count": summary.negative_count,
            "key_themes": summary.key_themes,
            "highlights": summary.highlights,
            "risks": summary.risks,
            "sources": summary.sources_used,
            "sources_breakdown": self.sources_breakdown(summary.articles),
            "last_updated": summary.last_updated.strftime("%Y-%m-%d %H:%M")
            if summary.last_updated
            else None,
            "articles_by_sentiment": {
                sentiment: [self._format_article_for_display(article) for article in articles]
                for sentiment, articles in summary.articles_by_sentiment().items()
            },
            "articles": [
                self._format_article_for_display(article) for article in summary.articles[:10]
            ],
        }


def is_available() -> bool:
    """Check if news service is available."""
    return YFINANCE_AVAILABLE
