"""
Comprehensive Dividend Kings Financial Analysis Tool

Analyzes dividend-paying stocks with focus on:
- Dividend history and sustainability
- Financial strength and safety metrics
- Valuation and growth potential
- Strategic investment recommendations
- Optional sentiment analysis from news sources
"""

import argparse
import csv
import os
import re
import sys
import warnings
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import yfinance as yf

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Import sentiment analysis libraries with fallback
try:
    from transformers import pipeline
    import feedparser
    import requests
    from bs4 import BeautifulSoup
    SENTIMENT_AVAILABLE = True
except ImportError:
    SENTIMENT_AVAILABLE = False
    print("⚠️  Sentiment analysis libraries not available. Install with: pip install transformers torch feedparser requests beautifulsoup4")

# Constants for sentiment analysis
DEFAULT_NEWS_DAYS = 30
MAX_ARTICLES = 10

# Constants for content extraction
MAX_CONTENT_LENGTH = 1000
MAX_SENTENCES_EXTRACT = 7
MAX_EXTRACT_LENGTH = 800
MIN_CONTENT_LENGTH = 100
FALLBACK_TEXT_LENGTH = 500
MIN_SENTENCE_LENGTH = 10
SENTENCE_SCORE_THRESHOLD_SHORT = 50
SENTENCE_SCORE_THRESHOLD_LONG = 100

def clean_news_text(text):
    """Clean news text by removing source attributions and bias-inducing elements.
    
    Removes:
        - News source names (CNN, Fox News, Reuters, etc.)
        - Attribution markers ("via", "|", "-")
        - Content in parentheses at end of text
        
    Args:
        text: Raw news text to clean
        
    Returns:
        str: Cleaned text without source attributions
    """
    if not text:
        return ""
    
    cleaned_text = text
    
    # Remove common source patterns that can bias sentiment analysis
    source_patterns = [
        r'\s*-\s*[A-Z][a-zA-Z\s]*TV\s*$',  # "- Azat TV", "- CNN TV", etc.
        r'\s*-\s*[A-Z][a-zA-Z\s]*News\s*$',  # "- Fox News", etc.
        r'\s*-\s*Reuters\s*$',
        r'\s*-\s*Bloomberg\s*$',
        r'\s*-\s*AP\s*$',
        r'\s*-\s*Associated Press\s*$',
        r'\s*-\s*[A-Z]{2,6}\s*$',  # Short acronyms like "WSJ", "CNBC"
        r'\s*\([^)]*\)\s*$',  # Remove content in parentheses at end
        r'\s*via\s+[A-Z][a-zA-Z\s]*$',  # "via Yahoo Finance", etc.
        r'\s*\|\s*[A-Z][a-zA-Z\s]*$',  # "| MarketWatch", etc.
    ]
    
    for pattern in source_patterns:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)
    
    return cleaned_text.strip()

def fetch_article_content(url, max_length=MAX_CONTENT_LENGTH):
    """Try to fetch full article content from URL.
    
    Args:
        url: Article URL to fetch
        max_length: Maximum content length to return
        
    Returns:
        str: Extracted article content or empty string
    """
    try:
        if not url or not url.startswith('http'):
            return ""
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return ""
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Try to find main content areas
        content_selectors = [
            'article', '.article-content', '.story-content', '.post-content',
            '.content', '.main-content', '.article-body', '.story-body',
            'main', '.entry-content', '.post-body'
        ]
        
        content_text = ""
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                content_text = content_elem.get_text(strip=True)
                break
        
        # Fallback to body text if no specific content found
        if not content_text:
            content_text = soup.get_text(strip=True)
        
        # Clean and truncate
        content_text = ' '.join(content_text.split())  # Remove extra whitespace
        if len(content_text) > max_length:
            content_text = content_text[:max_length] + "..."
        
        return content_text
        
    except Exception:
        return ""

def fetch_yf_news(ticker, days=DEFAULT_NEWS_DAYS, max_results=MAX_ARTICLES):
    """Fetch news from Yahoo Finance for a given ticker"""
    try:
        tk = yf.Ticker(ticker)
        news = tk.news or []
        cutoff = datetime.utcnow() - timedelta(days=days)
        items = []
        
        for n in news[:max_results]:
            # Skip invalid news items
            if not n or not isinstance(n, dict):
                continue
            
            # Check for new news format (content structure)
            content = n.get('content', {})
            if content:
                # New format with content wrapper
                title = content.get('title', '')
                summary = content.get('summary', content.get('description', ''))
                pub_date_str = content.get('pubDate', '')
                link = n.get('clickThroughUrl', {}).get('url', '') or n.get('canonicalUrl', {}).get('url', '')
                provider = content.get('provider', {}).get('displayName', '') or n.get('provider', {}).get('displayName', '')
                
                # Parse publication date
                pub = None
                if pub_date_str:
                    try:
                        # Parse ISO format like '2025-10-09T21:16:24Z'
                        pub = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    except (ValueError, TypeError):
                        continue
            else:
                # Old format - fallback
                title = n.get('title', '')
                summary = n.get('summary', '')
                link = n.get('link', '')
                provider = n.get('publisher', n.get('providerName', ''))
                
                # Try old timestamp format
                pub = None
                if n.get("providerPublishTime"):
                    try:
                        pub = datetime.utcfromtimestamp(n["providerPublishTime"])
                    except (ValueError, TypeError):
                        continue
            
            # Check date filter
            if pub and pub < cutoff:
                continue
                
            # Only add articles with at least a title
            if not title:
                continue
            
            # Try to get more content if available
            article_content = ""
            if link and len(summary) < 100:  # Only fetch if summary is short
                article_content = fetch_article_content(link, max_length=500)
            
            # Combine all available content
            full_description = summary
            if article_content and len(article_content) > len(summary):
                full_description = article_content
            elif article_content:
                full_description = f"{summary} {article_content}"
                
            items.append({
                "source": provider,
                "title": clean_news_text(title),
                "description": clean_news_text(full_description),
                "url": link,
                "publishedAt": pub.isoformat() if pub else None
            })
        return items
    except Exception as e:
        return []

def fetch_marketwatch_rss(ticker, days=DEFAULT_NEWS_DAYS, max_results=MAX_ARTICLES):
    """Fetch news from MarketWatch RSS feed"""
    try:
        # MarketWatch RSS feed for company news
        rss_url = f"https://feeds.marketwatch.com/marketwatch/company/{ticker.lower()}/"
        
        feed = feedparser.parse(rss_url)
        cutoff = datetime.utcnow() - timedelta(days=days)
        items = []
        
        for entry in feed.entries[:max_results]:
            try:
                # Parse publication date
                pub = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'published'):
                    # Try to parse string date
                    try:
                        pub = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
                    except:
                        continue
                
                if pub and pub < cutoff:
                    continue
                
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                link = entry.get('link', '')
                
                if title:
                    items.append({
                        "source": "MarketWatch",
                        "title": clean_news_text(title),
                        "description": clean_news_text(summary),
                        "url": link,
                        "publishedAt": pub.isoformat() if pub else None
                    })
            except Exception:
                continue
        
        return items
    except Exception:
        return []

def fetch_reuters_rss(ticker, days=DEFAULT_NEWS_DAYS, max_results=MAX_ARTICLES):
    """Fetch news from Reuters RSS feed"""
    try:
        # Reuters business news RSS
        rss_url = "https://feeds.reuters.com/reuters/businessNews"
        
        feed = feedparser.parse(rss_url)
        cutoff = datetime.utcnow() - timedelta(days=days)
        items = []
        
        # Filter articles that mention the ticker
        for entry in feed.entries[:50]:  # Check more entries to find relevant ones
            try:
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                
                # Check if ticker is mentioned in title or summary
                content_text = f"{title} {summary}".upper()
                if ticker.upper() not in content_text:
                    continue
                
                # Parse publication date
                pub = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                
                if pub and pub < cutoff:
                    continue
                
                link = entry.get('link', '')
                
                if title and len(items) < max_results:
                    items.append({
                        "source": "Reuters",
                        "title": clean_news_text(title),
                        "description": clean_news_text(summary),
                        "url": link,
                        "publishedAt": pub.isoformat() if pub else None
                    })
            except Exception:
                continue
        
        return items
    except Exception:
        return []

def fetch_seeking_alpha_rss(ticker, days=DEFAULT_NEWS_DAYS, max_results=MAX_ARTICLES):
    """Fetch news from Seeking Alpha RSS feed"""
    try:
        # Seeking Alpha RSS feed for specific ticker
        rss_url = f"https://seekingalpha.com/api/sa/combined/{ticker.upper()}.xml"
        
        feed = feedparser.parse(rss_url)
        cutoff = datetime.utcnow() - timedelta(days=days)
        items = []
        
        for entry in feed.entries[:max_results]:
            try:
                # Parse publication date
                pub = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                
                if pub and pub < cutoff:
                    continue
                
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                link = entry.get('link', '')
                
                if title:
                    items.append({
                        "source": "Seeking Alpha",
                        "title": clean_news_text(title),
                        "description": clean_news_text(summary),
                        "url": link,
                        "publishedAt": pub.isoformat() if pub else None
                    })
            except Exception:
                continue
        
        return items
    except Exception:
        return []

def fetch_google_news_rss(ticker, days=DEFAULT_NEWS_DAYS, max_results=MAX_ARTICLES):
    """Fetch news from Google News RSS feed"""
    try:
        # Google News RSS feed for ticker
        query = f"{ticker} stock OR {ticker} earnings OR {ticker} dividend"
        encoded_query = quote_plus(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        
        feed = feedparser.parse(rss_url)
        cutoff = datetime.utcnow() - timedelta(days=days)
        items = []
        
        for entry in feed.entries[:max_results]:
            try:
                # Parse publication date
                pub = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                
                if pub and pub < cutoff:
                    continue
                
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                link = entry.get('link', '')
                
                # Extract source from title (Google News format often includes source)
                source = "Google News"
                if ' - ' in title:
                    parts = title.rsplit(' - ', 1)
                    if len(parts) == 2:
                        title = parts[0]
                        source = parts[1]
                
                if title:
                    items.append({
                        "source": source,
                        "title": clean_news_text(title),
                        "description": clean_news_text(summary),
                        "url": link,
                        "publishedAt": pub.isoformat() if pub else None
                    })
            except Exception:
                continue
        
        return items
    except Exception:
        return []

def fetch_benzinga_rss(ticker, days=DEFAULT_NEWS_DAYS, max_results=MAX_ARTICLES):
    """Fetch news from Benzinga RSS feed"""
    try:
        # Benzinga RSS feed
        rss_url = "https://www.benzinga.com/feed"
        
        feed = feedparser.parse(rss_url)
        cutoff = datetime.utcnow() - timedelta(days=days)
        items = []
        
        # Filter articles that mention the ticker
        for entry in feed.entries[:100]:  # Check more entries to find relevant ones
            try:
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                
                # Check if ticker is mentioned in title or summary
                content_text = f"{title} {summary}".upper()
                if ticker.upper() not in content_text:
                    continue
                
                # Parse publication date
                pub = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                
                if pub and pub < cutoff:
                    continue
                
                link = entry.get('link', '')
                
                if title and len(items) < max_results:
                    items.append({
                        "source": "Benzinga",
                        "title": clean_news_text(title),
                        "description": clean_news_text(summary),
                        "url": link,
                        "publishedAt": pub.isoformat() if pub else None
                    })
            except Exception:
                continue
        
        return items
    except Exception:
        return []

def fetch_all_news_sources(ticker, days=DEFAULT_NEWS_DAYS, verbose=False):
    """Fetch news from all available sources and combine them"""
    all_articles = []
    
    # List of news fetching functions
    news_sources = [
        ("Yahoo Finance", fetch_yf_news),
        ("MarketWatch", fetch_marketwatch_rss),
        ("Reuters", fetch_reuters_rss),
        ("Google News", fetch_google_news_rss),
        ("Seeking Alpha", fetch_seeking_alpha_rss),
        ("Benzinga", fetch_benzinga_rss)
    ]
    
    for source_name, fetch_func in news_sources:
        try:
            if verbose:
                print(f"   📰 Fetching from {source_name}...", end=" ")
            
            articles = fetch_func(ticker, days, MAX_ARTICLES // len(news_sources))
            
            if verbose:
                print(f"({len(articles)} articles)")
            
            all_articles.extend(articles)
            
        except Exception as e:
            if verbose:
                print(f"(error: {str(e)[:30]}...)")
            continue
    
    # Remove duplicates based on title similarity
    unique_articles = []
    seen_titles = set()
    
    for article in all_articles:
        title = article.get('title', '').lower().strip()
        # Create a simplified version for comparison
        title_key = re.sub(r'[^\w\s]', '', title)[:50]
        
        if title_key not in seen_titles and title_key:
            seen_titles.add(title_key)
            unique_articles.append(article)
    
    # Sort by publication date (newest first)
    try:
        unique_articles.sort(key=lambda x: x.get('publishedAt', ''), reverse=True)
    except (TypeError, KeyError):
        pass
    
    # Limit to MAX_ARTICLES
    return unique_articles[:MAX_ARTICLES]

def extract_key_financial_content(text, verbose=False):
    """Extract the most important financial content from article text"""
    if not text:
        return ""
    
    # Use the centralized text cleaning function
    cleaned_text = clean_news_text(text)
    
    # Split into sentences for better analysis
    sentences = [
        s.strip() for s in cleaned_text.replace('\n', ' ').split('.')
        if s.strip() and len(s.strip()) > MIN_SENTENCE_LENGTH
    ]
    
    # Financial keywords that indicate important content
    financial_keywords = [
        # Core financial metrics
        'revenue', 'profit', 'earnings', 'sales', 'income', 'margin', 'cash flow',
        'debt', 'investment', 'stock', 'share', 'market', 'quarterly', 'annual',
        
        # Forecasts and guidance
        'guidance', 'outlook', 'forecast', 'estimates', 'beat', 'miss', 'exceed',
        
        # Analyst actions
        'outperform', 'underperform', 'upgrade', 'downgrade', 'buy', 'sell', 'hold',
        'target price', 'analyst', 'rating', 'recommendation',
        
        # Price movements
        'rises', 'surges', 'climbs', 'jumps', 'gains', 'falls', 'drops', 'declines', 'plunges',
        
        # Dividend-specific keywords
        'dividend', 'dividend increase', 'dividend cut', 'dividend yield',
        'dividend payment', 'dividend payout', 'dividend king', 'dividend aristocrat',
        'dividend growth', 'dividend policy', 'dividend coverage', 'payout ratio',
        'ex-dividend', 'record date', 'payment date', 'special dividend',
        'quarterly dividend', 'annual dividend', 'dividend suspension', 'dividend reinstatement',
        
        # Performance indicators
        'free cash flow', 'operating margin', 'net income', 'gross margin',
        'return on equity', 'return on assets', 'earnings per share',
        'book value', 'price to earnings',
        
        # Sentiment and performance
        'strong', 'weak', 'positive', 'negative', 'bullish', 'bearish',
        'optimistic', 'pessimistic', 'recovery', 'improvement', 'decline',
        'success', 'failure', 'challenge', 'opportunity',
        
        # Corporate actions
        'acquisition', 'merger', 'expansion', 'restructuring', 'cost cutting', 'efficiency'
    ]
    
    # Score sentences based on financial keyword density and length
    scored_sentences = []
    for sentence in sentences:
        score = 0
        lower_sentence = sentence.lower()
        
        # Count keyword matches
        for keyword in financial_keywords:
            if keyword in lower_sentence:
                score += 1
        
        # Bonus for longer, more informative sentences
        if len(sentence) > SENTENCE_SCORE_THRESHOLD_SHORT:
            score += 1
        if len(sentence) > SENTENCE_SCORE_THRESHOLD_LONG:
            score += 1
        
        if score > 0:
            scored_sentences.append((score, sentence))
    
    # Sort by score and return more comprehensive content
    scored_sentences.sort(reverse=True, key=lambda x: x[0])
    
    if scored_sentences:
        # Take more sentences for better context
        selected_sentences = []
        total_length = 0
        max_sentences = MAX_SENTENCES_EXTRACT
        max_length = MAX_EXTRACT_LENGTH
        
        for score, sentence in scored_sentences:
            if len(selected_sentences) >= max_sentences or total_length >= max_length:
                break
            selected_sentences.append(sentence)
            total_length += len(sentence)
        
        result = ' '.join(selected_sentences)
        
        # If we still don't have enough content, include more of the original text
        if len(result) < MIN_CONTENT_LENGTH and len(cleaned_text) > len(result):
            result = cleaned_text[:FALLBACK_TEXT_LENGTH] + "..." if len(cleaned_text) > FALLBACK_TEXT_LENGTH else cleaned_text
        
        return result
    else:
        # No financial keywords found, return substantial portion of original text
        return cleaned_text[:FALLBACK_TEXT_LENGTH] + "..." if len(cleaned_text) > FALLBACK_TEXT_LENGTH else cleaned_text

def score_article(article, sentiment_classifier, verbose=False):
    """Score a single article using sentiment analysis with enhanced content extraction.
    
    Args:
        article: Article dict with 'title' and 'description' keys
        sentiment_classifier: Initialized sentiment analysis pipeline
        verbose: Whether to print detailed scoring information
        
    Returns:
        tuple: (sentiment_score, confidence) where sentiment_score is between -1 and 1
    """
    if not article or not sentiment_classifier:
        return 0, 0
    
    title = article.get('title', '')
    description = article.get('description', '')
    
    # Combine title and description for maximum context
    full_text = f"{title}. {description}" if description else title
    
    # Extract comprehensive financial content
    key_content = extract_key_financial_content(full_text, verbose)
    
    if not key_content or len(key_content.strip()) < 20:
        if verbose:
            print(f"   ⚠️  '{title[:40]}...' -> Insufficient content for analysis")
        return 0, 0
    
    try:
        # Truncate if too long for the model (most sentiment models have 512 token limit)
        if len(key_content) > 400:
            # Take first 200 and last 200 characters to preserve context
            key_content = key_content[:200] + "..." + key_content[-200:]
        
        # Get sentiment with confidence scores
        result = sentiment_classifier(key_content)
        
        if isinstance(result, list) and len(result) > 0:
            result = result[0]
        
        label = result.get('label', 'NEUTRAL')
        confidence = result.get('score', 0)
        
        # Convert to sentiment score: POSITIVE = +1, NEGATIVE = -1, NEUTRAL = 0
        if label == 'POSITIVE':
            sentiment_score = confidence
        elif label == 'NEGATIVE':
            sentiment_score = -confidence
        else:
            sentiment_score = 0
        
        if verbose:
            content_preview = key_content[:100] + "..." if len(key_content) > 100 else key_content
            print(f"   📰 '{title[:50]}...'")
            print(f"       Content: '{content_preview}'")
            print(f"       -> {label} (conf: {confidence:.3f}, score: {sentiment_score:+.3f})")
        
        return sentiment_score, confidence
        
    except Exception as e:
        if verbose:
            print(f"   ❌ Error scoring article '{title[:40]}...': {e}")
        return 0, 0

def analyze_news_sentiment(ticker, days=DEFAULT_NEWS_DAYS, verbose=False, sentiment_classifier=None):
    """Analyze news sentiment for a ticker with enhanced content processing"""
    if not SENTIMENT_AVAILABLE:
        return 0, 0, 0  # neutral sentiment, 0 confidence, 0 articles
    
    try:
        # Initialize sentiment classifier if not provided
        if sentiment_classifier is None:
            sentiment_classifier = pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sst-2-english",
                tokenizer="distilbert-base-uncased-finetuned-sst-2-english"
            )
        
        if verbose:
            print(f"🔍 Fetching news for {ticker} from multiple sources...")
        
        # Fetch news from all available sources
        articles = fetch_all_news_sources(ticker, days, verbose)
        
        if not articles:
            if verbose:
                print(f"   ⚠️  No recent news found for {ticker} from any source")
            return 0, 0, 0
        
        if verbose:
            print(f"   📰 Found {len(articles)} total articles from all sources for sentiment analysis")
            print(f"   🔬 Analyzing content with enhanced extraction...")
        
        # Score all articles with enhanced processing
        sentiment_scores = []
        confidence_scores = []
        
        for i, article in enumerate(articles):
            if verbose:
                print(f"   📄 Article {i+1}/{len(articles)}:")
            
            score, confidence = score_article(article, sentiment_classifier, verbose)
            if confidence > 0:  # Only include articles with valid sentiment
                sentiment_scores.append(score)
                confidence_scores.append(confidence)
        
        if not sentiment_scores:
            if verbose:
                print(f"   ⚠️  No articles had sufficient content for sentiment analysis")
            return 0, 0, len(articles)
        
        # Calculate weighted average sentiment with bias correction
        total_weight = sum(confidence_scores)
        if total_weight > 0:
            weighted_sentiment = sum(s * c for s, c in zip(sentiment_scores, confidence_scores)) / total_weight
        else:
            weighted_sentiment = 0
        
        # Apply bias correction for small sample sizes
        if len(sentiment_scores) < 3:
            # Reduce extreme sentiment for small samples
            weighted_sentiment *= 0.7
        
        # Calculate average confidence
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
        
        if verbose:
            print(f"   📊 Raw Sentiment: {weighted_sentiment:+.3f}, Confidence: {avg_confidence:.3f}")
            print(f"   📊 Articles with content: {len(sentiment_scores)}/{len(articles)}")
            
            # Show distribution of sentiments
            positive_count = sum(1 for s in sentiment_scores if s > 0.1)
            negative_count = sum(1 for s in sentiment_scores if s < -0.1)
            neutral_count = len(sentiment_scores) - positive_count - negative_count
            print(f"   📊 Sentiment Distribution: {positive_count} positive, {neutral_count} neutral, {negative_count} negative")
        
        return weighted_sentiment, avg_confidence, len(sentiment_scores)
        
    except Exception as e:
        if verbose:
            print(f"   ❌ Error in sentiment analysis: {e}")
        return 0, 0, 0

def comprehensive_valuation_assessment(trailing_pe, forward_pe, peg_ratio, price_to_sales, price_to_book, ev_ebitda):
    """Comprehensive valuation assessment based on multiple metrics.
    
    Returns valuation category based on weighted scoring of available metrics.
    """
    if all(x is None for x in [trailing_pe, forward_pe, peg_ratio, price_to_sales, price_to_book, ev_ebitda]):
        return "No Data"
    
    score = 0
    metrics_count = 0
    
    # Trailing P/E assessment
    if trailing_pe is not None:
        if trailing_pe <= 15:
            score += 3
        elif trailing_pe <= 25:
            score += 2
        elif trailing_pe <= 35:
            score += 1
        metrics_count += 1
    
    # Forward P/E assessment
    if forward_pe is not None:
        if forward_pe <= 15:
            score += 3
        elif forward_pe <= 25:
            score += 2
        elif forward_pe <= 30:
            score += 1
        metrics_count += 1
    
    # PEG Ratio assessment
    if peg_ratio is not None:
        if peg_ratio <= 1.0:
            score += 3
        elif peg_ratio <= 1.5:
            score += 2
        elif peg_ratio <= 2.0:
            score += 1
        metrics_count += 1
    
    # Price to Sales assessment  
    if price_to_sales is not None:
        if price_to_sales <= 2.0:
            score += 3
        elif price_to_sales <= 4.0:
            score += 2
        elif price_to_sales <= 6.0:
            score += 1
        metrics_count += 1
    
    # Price to Book assessment
    if price_to_book is not None:
        if price_to_book <= 1.5:
            score += 3
        elif price_to_book <= 3.0:
            score += 2
        elif price_to_book <= 5.0:
            score += 1
        metrics_count += 1
    
    # EV/EBITDA assessment
    if ev_ebitda is not None:
        if ev_ebitda <= 10:
            score += 3
        elif ev_ebitda <= 15:
            score += 2
        elif ev_ebitda <= 20:
            score += 1
        metrics_count += 1
    
    if metrics_count == 0:
        return "No Data"
    
    avg_score = score / metrics_count
    
    if avg_score >= 2.5:
        return "Undervalued"
    elif avg_score >= 1.5:
        return "Fair"
    else:
        return "Overvalued"

def strategic_analysis(stock, symbol, market_cap, trailing_pe, dividend_yield, debt_to_equity, ev_ebitda, current_ratio):
    """
    Comprehensive dividend investing strategy based on proven best practices.
    
    Scoring framework (100 points total):
    - Dividend Quality & Sustainability: 25 points
    - Dividend Growth Potential: 20 points
    - Financial Strength & Safety: 20 points
    - Valuation & Value: 15 points
    - Business Quality & Efficiency: 12 points
    - Risk Management: 8 points
    
    Returns:
        tuple: (strategy_recommendation, percentage_score, analysis_details)
    """
    
    # Initialize scoring system
    total_score = 0
    max_possible_score = 0
    analysis_details = []
    red_flags = []
    green_flags = []
    
    # Get comprehensive data
    dividend_history = get_comprehensive_dividend_history(stock, symbol)
    historical_data = get_historical_data(stock, symbol)
    info = stock.info if hasattr(stock, 'info') else {}
    
    # Key financial metrics
    payout_ratio = info.get('payoutRatio', None)
    free_cash_flow = info.get('freeCashflow', None)
    total_cash = info.get('totalCash', None)
    operating_cash_flow = info.get('operatingCashflow', None)
    shares_outstanding = info.get('sharesOutstanding', None)
    revenue_growth = info.get('revenueGrowth', None)
    earnings_growth = info.get('earningsGrowth', None)
    roe = info.get('returnOnEquity', None)
    profit_margins = info.get('profitMargins', None)
    
    # =================================================================
    # CORE PRINCIPLE 1: DIVIDEND QUALITY & SUSTAINABILITY (25 points)
    # =================================================================
    max_possible_score += 25
    quality_score = 0
    
    # 1A. Dividend History & Consistency (15 points)
    if dividend_history:
        years_of_payments = dividend_history.get('years_of_payments', 0)
        consistency_rate = dividend_history.get('consistency_rate', 0)
        
        # Years of consecutive payments
        if years_of_payments >= 25:  # Dividend Aristocrat territory
            quality_score += 8
            green_flags.append(f"Dividend Aristocrat: {years_of_payments} years of payments")
        elif years_of_payments >= 10:  # Strong track record
            quality_score += 6
            green_flags.append(f"Strong dividend history: {years_of_payments} years")
        elif years_of_payments >= 5:  # Minimum acceptable
            quality_score += 4
            analysis_details.append(f"Moderate dividend history: {years_of_payments} years")
        elif years_of_payments >= 2:
            quality_score += 2
            analysis_details.append(f"Short dividend history: {years_of_payments} years")
        else:
            red_flags.append("Very short or no dividend history")
        
        # Consistency rate
        if consistency_rate >= 95:
            quality_score += 4
            green_flags.append(f"Excellent consistency: {consistency_rate:.0f}%")
        elif consistency_rate >= 85:
            quality_score += 3
            analysis_details.append(f"Good consistency: {consistency_rate:.0f}%")
        elif consistency_rate >= 70:
            quality_score += 2
            analysis_details.append(f"Moderate consistency: {consistency_rate:.0f}%")
        else:
            quality_score += 1
            red_flags.append(f"Poor dividend consistency: {consistency_rate:.0f}%")
        
        # Recent dividend cuts check
        annual_divs = dividend_history.get('annual_dividends', {})
        if len(annual_divs) >= 3:
            recent_years = sorted(annual_divs.keys())[-3:]
            recent_cuts = 0
            for i in range(1, len(recent_years)):
                if annual_divs[recent_years[i]] < annual_divs[recent_years[i-1]]:
                    recent_cuts += 1
            
            if recent_cuts == 0:
                quality_score += 3
                green_flags.append("No recent dividend cuts")
            elif recent_cuts == 1:
                quality_score += 1
                analysis_details.append("One recent dividend cut")
            else:
                red_flags.append("Multiple recent dividend cuts")
    else:
        red_flags.append("No dividend payment history")
    
    # 1B. Payout Ratio Analysis (10 points)
    if payout_ratio is not None:
        payout_pct = payout_ratio * 100
        
        # Best practice: 30-70% payout ratio
        if 30 <= payout_pct <= 70:
            quality_score += 10
            green_flags.append(f"Optimal payout ratio: {payout_pct:.1f}%")
        elif 20 <= payout_pct < 30:
            quality_score += 8
            analysis_details.append(f"Conservative payout: {payout_pct:.1f}% (room for growth)")
        elif 70 < payout_pct <= 85:
            quality_score += 6
            analysis_details.append(f"High but manageable payout: {payout_pct:.1f}%")
        elif payout_pct < 20:
            quality_score += 5
            analysis_details.append(f"Very low payout: {payout_pct:.1f}% (may indicate growth focus)")
        elif 85 < payout_pct <= 100:
            quality_score += 3
            red_flags.append(f"Very high payout ratio: {payout_pct:.1f}%")
        else:
            quality_score += 0
            red_flags.append(f"Unsustainable payout ratio: {payout_pct:.1f}%")
    else:
        analysis_details.append("Payout ratio data not available")
    
    total_score += quality_score
    
    # =================================================================
    # CORE PRINCIPLE 2: DIVIDEND GROWTH POTENTIAL (20 points)
    # =================================================================
    max_possible_score += 20
    growth_score = 0
    
    # 2A. Historical Dividend Growth (12 points)
    if dividend_history:
        div_cagr = dividend_history.get('dividend_cagr', 0)
        recent_growth = dividend_history.get('recent_avg_growth', 0)
        
        # Long-term dividend CAGR
        if div_cagr >= 8:
            growth_score += 7
            green_flags.append(f"Excellent dividend growth: {div_cagr:.1f}% CAGR")
        elif div_cagr >= 5:
            growth_score += 5
            green_flags.append(f"Strong dividend growth: {div_cagr:.1f}% CAGR")
        elif div_cagr >= 3:
            growth_score += 3
            analysis_details.append(f"Moderate dividend growth: {div_cagr:.1f}% CAGR")
        elif div_cagr >= 0:
            growth_score += 1
            analysis_details.append(f"Stable dividends: {div_cagr:.1f}% CAGR")
        else:
            red_flags.append(f"Declining dividends: {div_cagr:.1f}% CAGR")
        
        # Recent growth trend (5-year)
        if recent_growth >= 6:
            growth_score += 5
            green_flags.append(f"Accelerating growth: {recent_growth:.1f}% recent")
        elif recent_growth >= 3:
            growth_score += 3
            analysis_details.append(f"Steady recent growth: {recent_growth:.1f}%")
        elif recent_growth >= 0:
            growth_score += 1
            analysis_details.append(f"Stable recent dividends: {recent_growth:.1f}%")
        else:
            red_flags.append(f"Recent dividend decline: {recent_growth:.1f}%")
    
    # 2B. Earnings Growth Supporting Dividends (8 points)
    if earnings_growth is not None:
        earnings_growth_pct = earnings_growth * 100
        if earnings_growth_pct >= 10:
            growth_score += 8
            green_flags.append(f"Strong earnings growth: {earnings_growth_pct:.1f}%")
        elif earnings_growth_pct >= 5:
            growth_score += 6
            analysis_details.append(f"Good earnings growth: {earnings_growth_pct:.1f}%")
        elif earnings_growth_pct >= 0:
            growth_score += 3
            analysis_details.append(f"Positive earnings growth: {earnings_growth_pct:.1f}%")
        else:
            growth_score += 0
            red_flags.append(f"Declining earnings: {earnings_growth_pct:.1f}%")
    elif revenue_growth is not None:
        revenue_growth_pct = revenue_growth * 100
        if revenue_growth_pct >= 8:
            growth_score += 4
            analysis_details.append(f"Strong revenue growth: {revenue_growth_pct:.1f}%")
        elif revenue_growth_pct >= 3:
            growth_score += 2
            analysis_details.append(f"Moderate revenue growth: {revenue_growth_pct:.1f}%")
    
    total_score += growth_score
    
    # =================================================================
    # CORE PRINCIPLE 3: FINANCIAL STRENGTH & SAFETY (20 points)
    # =================================================================
    max_possible_score += 20
    safety_score = 0
    
    # 3A. Balance Sheet Strength (12 points)
    # Debt-to-Equity Analysis
    if debt_to_equity is not None:
        if debt_to_equity <= 0.3:
            safety_score += 6
            green_flags.append(f"Conservative debt: {debt_to_equity:.2f} D/E")
        elif debt_to_equity <= 0.6:
            safety_score += 4
            analysis_details.append(f"Moderate debt: {debt_to_equity:.2f} D/E")
        elif debt_to_equity <= 1.0:
            safety_score += 2
            analysis_details.append(f"Elevated debt: {debt_to_equity:.2f} D/E")
        else:
            safety_score += 0
            red_flags.append(f"High debt risk: {debt_to_equity:.2f} D/E")
    
    # Current Ratio (Liquidity)
    if current_ratio is not None:
        if current_ratio >= 2.0:
            safety_score += 3
            green_flags.append(f"Strong liquidity: {current_ratio:.2f}")
        elif current_ratio >= 1.5:
            safety_score += 2
            analysis_details.append(f"Good liquidity: {current_ratio:.2f}")
        elif current_ratio >= 1.0:
            safety_score += 1
            analysis_details.append(f"Adequate liquidity: {current_ratio:.2f}")
        else:
            red_flags.append(f"Liquidity concerns: {current_ratio:.2f}")
    
    # Cash Position
    if total_cash and market_cap:
        cash_ratio = (total_cash / market_cap) * 100
        if cash_ratio >= 10:
            safety_score += 3
            green_flags.append(f"Strong cash position: {cash_ratio:.1f}%")
        elif cash_ratio >= 5:
            safety_score += 2
            analysis_details.append(f"Good cash reserves: {cash_ratio:.1f}%")
        elif cash_ratio >= 2:
            safety_score += 1
            analysis_details.append(f"Adequate cash: {cash_ratio:.1f}%")
    
    # 3B. Cash Flow Coverage (8 points)
    if free_cash_flow and dividend_history and shares_outstanding:
        annual_dividend = dividend_history.get('current_annual_dividend', 0)
        total_dividend_payment = annual_dividend * shares_outstanding
        
        if total_dividend_payment > 0:
            fcf_coverage = free_cash_flow / total_dividend_payment
            if fcf_coverage >= 2.0:
                safety_score += 8
                green_flags.append(f"Excellent FCF coverage: {fcf_coverage:.1f}x")
            elif fcf_coverage >= 1.5:
                safety_score += 6
                green_flags.append(f"Strong FCF coverage: {fcf_coverage:.1f}x")
            elif fcf_coverage >= 1.2:
                safety_score += 4
                analysis_details.append(f"Adequate FCF coverage: {fcf_coverage:.1f}x")
            elif fcf_coverage >= 1.0:
                safety_score += 2
                red_flags.append(f"Minimal FCF coverage: {fcf_coverage:.1f}x")
            else:
                red_flags.append(f"Insufficient FCF coverage: {fcf_coverage:.1f}x")
    
    total_score += safety_score
    
    # =================================================================
    # CORE PRINCIPLE 4: VALUATION & VALUE (15 points)
    # =================================================================
    max_possible_score += 15
    value_score = 0
    
    # 4A. Dividend Yield Assessment (8 points)
    if dividend_yield is not None:
        # Context-aware yield evaluation
        if 2.5 <= dividend_yield <= 6.0:  # Sweet spot for most dividend stocks
            value_score += 6
            green_flags.append(f"Attractive yield: {dividend_yield:.2f}%")
        elif 2.0 <= dividend_yield < 2.5:
            value_score += 4
            analysis_details.append(f"Moderate yield: {dividend_yield:.2f}%")
        elif 6.0 < dividend_yield <= 8.0:
            value_score += 4
            analysis_details.append(f"High yield: {dividend_yield:.2f}% (verify sustainability)")
        elif 1.5 <= dividend_yield < 2.0:
            value_score += 3
            analysis_details.append(f"Lower yield: {dividend_yield:.2f}% (growth focus?)")
        elif dividend_yield > 8.0:
            value_score += 2
            red_flags.append(f"Very high yield: {dividend_yield:.2f}% (potential red flag)")
        else:
            value_score += 1
            analysis_details.append(f"Low yield: {dividend_yield:.2f}%")
        
        # Yield vs 10-year average check
        if dividend_history:
            annual_divs = dividend_history.get('annual_dividends', {})
            if len(annual_divs) >= 3:
                recent_avg_div = sum(list(annual_divs.values())[-3:]) / 3
                current_price = historical_data.get('current_price', None)
                if current_price:
                    historical_yield = (recent_avg_div / current_price) * 100
                    yield_premium = dividend_yield - historical_yield
                    if yield_premium > 1.0:
                        value_score += 2
                        analysis_details.append(f"Above historical yield by {yield_premium:.1f}%")
    
    # 4B. P/E Ratio Analysis (7 points)
    if trailing_pe is not None:
        if trailing_pe <= 15:
            value_score += 7
            green_flags.append(f"Attractive P/E: {trailing_pe:.1f}")
        elif trailing_pe <= 20:
            value_score += 5
            analysis_details.append(f"Fair P/E: {trailing_pe:.1f}")
        elif trailing_pe <= 25:
            value_score += 3
            analysis_details.append(f"Moderate P/E: {trailing_pe:.1f}")
        elif trailing_pe <= 30:
            value_score += 1
            analysis_details.append(f"High P/E: {trailing_pe:.1f}")
        else:
            red_flags.append(f"Very high P/E: {trailing_pe:.1f}")
    
    total_score += value_score
    
    # =================================================================
    # CORE PRINCIPLE 5: BUSINESS QUALITY & EFFICIENCY (12 points)
    # =================================================================
    max_possible_score += 12
    quality_business_score = 0
    
    # 5A. Return on Equity (6 points)
    if roe is not None:
        roe_pct = roe * 100
        if roe_pct >= 15:
            quality_business_score += 6
            green_flags.append(f"Excellent ROE: {roe_pct:.1f}%")
        elif roe_pct >= 10:
            quality_business_score += 4
            analysis_details.append(f"Good ROE: {roe_pct:.1f}%")
        elif roe_pct >= 5:
            quality_business_score += 2
            analysis_details.append(f"Fair ROE: {roe_pct:.1f}%")
        else:
            red_flags.append(f"Poor ROE: {roe_pct:.1f}%")
    
    # 5B. Profit Margins (6 points)
    if profit_margins is not None:
        margin_pct = profit_margins * 100
        if margin_pct >= 15:
            quality_business_score += 6
            green_flags.append(f"Excellent margins: {margin_pct:.1f}%")
        elif margin_pct >= 10:
            quality_business_score += 4
            analysis_details.append(f"Good margins: {margin_pct:.1f}%")
        elif margin_pct >= 5:
            quality_business_score += 2
            analysis_details.append(f"Fair margins: {margin_pct:.1f}%")
        else:
            red_flags.append(f"Poor margins: {margin_pct:.1f}%")
    
    total_score += quality_business_score
    
    # =================================================================
    # CORE PRINCIPLE 6: RISK MANAGEMENT (8 points)
    # =================================================================
    max_possible_score += 8
    risk_score = 8  # Start with full points, deduct for risks
    
    # Volatility Risk
    volatility = historical_data.get('volatility_1y', None)
    if volatility is not None:
        if volatility > 35:
            risk_score -= 3
            red_flags.append(f"High volatility: {volatility:.1f}%")
        elif volatility > 25:
            risk_score -= 1
            analysis_details.append(f"Moderate volatility: {volatility:.1f}%")
        else:
            green_flags.append(f"Low volatility: {volatility:.1f}%")
    
    # Drawdown Risk
    max_drawdown = historical_data.get('max_drawdown', None)
    if max_drawdown is not None:
        if max_drawdown < -40:
            risk_score -= 3
            red_flags.append(f"Severe drawdown risk: {max_drawdown:.1f}%")
        elif max_drawdown < -25:
            risk_score -= 1
            analysis_details.append(f"Moderate drawdown: {max_drawdown:.1f}%")
    
    # Sector concentration risk (if available)
    sector = info.get('sector', None)
    if sector in ['Real Estate', 'Utilities']:  # High dividend sectors but cyclical
        analysis_details.append(f"Sector note: {sector} (cyclical dividend sector)")
    
    total_score += max(risk_score, 0)
    
    # =================================================================
    # FINAL SCORING & RECOMMENDATION
    # =================================================================
    
    percentage_score = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
    
    # Advanced Decision Matrix
    critical_red_flags = len([flag for flag in red_flags if any(word in flag.lower() for word in 
                            ['unsustainable', 'cuts', 'declining', 'insufficient', 'severe'])])
    
    strong_green_flags = len([flag for flag in green_flags if any(word in flag.lower() for word in 
                            ['excellent', 'aristocrat', 'strong', 'attractive'])])
    
    # Determine final recommendation
    if percentage_score >= 85 and critical_red_flags == 0:
        strategy = "STRONG BUY"
        decision = "Outstanding dividend stock with exceptional quality across all metrics"
    elif percentage_score >= 75 and critical_red_flags <= 1:
        strategy = "BUY"
        decision = "High-quality dividend stock with strong fundamentals"
    elif percentage_score >= 65 and critical_red_flags <= 2:
        strategy = "CONSIDER"
        decision = "Solid dividend investment with minor concerns to monitor"
    elif percentage_score >= 50:
        strategy = "HOLD/WATCH"
        decision = "Mixed dividend profile, suitable for income but limited growth"
    elif percentage_score >= 35:
        strategy = "WEAK HOLD"
        decision = "Below-average dividend stock, consider alternatives"
    else:
        strategy = "AVOID"
        decision = "Poor dividend investment with significant risks"
    
    # Compile final analysis
    final_details = []
    
    # Add summary scores
    final_details.append(f"Overall Score: {percentage_score:.1f}% ({total_score}/{max_possible_score})")
    final_details.append(f"Quality Score: {quality_score}/25")
    final_details.append(f"Growth Score: {growth_score}/20") 
    final_details.append(f"Safety Score: {safety_score}/20")
    final_details.append(f"Value Score: {value_score}/15")
    final_details.append(f"Business Quality: {quality_business_score}/12")
    final_details.append(f"Risk Management: {max(risk_score, 0)}/8")
    
    # Add key insights
    if green_flags:
        final_details.append("✅ STRENGTHS:")
        final_details.extend([f"  • {flag}" for flag in green_flags[:5]])  # Top 5 strengths
    
    if red_flags:
        final_details.append("⚠️ CONCERNS:")
        final_details.extend([f"  • {flag}" for flag in red_flags[:5]])  # Top 5 concerns
    
    if analysis_details:
        final_details.append("📊 ADDITIONAL NOTES:")
        final_details.extend([f"  • {detail}" for detail in analysis_details[:3]])  # Top 3 notes
    
    final_details.append(f"📋 DECISION: {decision}")
    
    # Add best practices summary
    final_details.append("🎯 DIVIDEND INVESTING BEST PRACTICES APPLIED:")
    final_details.append("  • Quality over yield chasing")
    final_details.append("  • Sustainable payout ratios (30-70%)")
    final_details.append("  • Consistent growth track record")
    final_details.append("  • Strong balance sheet analysis")
    final_details.append("  • Business quality assessment")
    final_details.append("  • Risk-adjusted evaluation")
    
    return strategy, percentage_score, final_details

def get_historical_data(stock, symbol):
    """Get comprehensive historical data for a stock.
    
    Returns dict containing:
        - Price returns (1y, 3y, 5y)
        - Volatility (1-year)
        - Maximum drawdown
        - 52-week high/low prices
        - Price vs 52-week high
    """
    try:
        # Get historical price data (5 years)
        hist = stock.history(period="5y")
        
        if hist.empty:
            return {}
        
        # Current price and 52-week range
        current_price = hist['Close'].iloc[-1]
        year_high = hist['High'].rolling(window=252).max().iloc[-1]  # 252 trading days ≈ 1 year
        year_low = hist['Low'].rolling(window=252).min().iloc[-1]
        
        # Calculate returns
        price_1y_return = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-252]) - 1) * 100 if len(hist) >= 252 else None
        price_3y_return = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-756]) - 1) * 100 if len(hist) >= 756 else None
        price_5y_return = ((hist['Close'].iloc[-1] / hist['Close'].iloc[0]) - 1) * 100 if len(hist) >= 1260 else None
        
        # Calculate volatility (1-year)
        returns = hist['Close'].pct_change().dropna()
        volatility_1y = returns.tail(252).std() * np.sqrt(252) * 100 if len(returns) >= 252 else None
        
        # Calculate max drawdown
        rolling_max = hist['Close'].expanding().max()
        drawdown = (hist['Close'] - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100
        
        # Position relative to 52-week high
        price_vs_52w_high = ((current_price - year_high) / year_high) * 100
        
        return {
            'price_1y_return': price_1y_return,
            'price_3y_return': price_3y_return, 
            'price_5y_return': price_5y_return,
            'volatility_1y': volatility_1y,
            'max_drawdown': max_drawdown,
            'price_vs_52w_high': price_vs_52w_high,
            'price_52w_high': year_high,
            'price_52w_low': year_low
        }
    
    except Exception as e:
        print(f"Error getting historical data for {symbol}: {str(e)}")
        return {}

def get_comprehensive_dividend_history(stock, symbol):
    """Get comprehensive dividend history and statistics.
    
    Calculates:
        - Annual and quarterly dividend summaries
        - Dividend growth CAGR
        - Consistency metrics
        - Recent performance trends
        
    Returns:
        dict: Comprehensive dividend statistics or None if no dividend history
    """
    try:
        # Get all available dividend data
        dividends = stock.dividends
        if dividends.empty:
            return None
        
        # Convert to DataFrame for easier analysis
        div_df = dividends.to_frame('dividend')
        div_df['year'] = div_df.index.year
        div_df['quarter'] = div_df.index.quarter
        div_df['date'] = div_df.index
        
        # Calculate annual dividends
        annual_dividends = div_df.groupby('year')['dividend'].sum().sort_index()
        
        # Calculate quarterly statistics
        quarterly_stats = div_df.groupby(['year', 'quarter'])['dividend'].sum().reset_index()
        
        # Get current quarter dividend from official data
        from datetime import date
        today = date.today()
        current_year = today.year
        current_quarter = (today.month - 1) // 3 + 1
        
        current_quarter_dividend = None
        
        if not quarterly_stats.empty:
            # Find the dividend for current quarter
            current_q_data = quarterly_stats[
                (quarterly_stats['year'] == current_year) & 
                (quarterly_stats['quarter'] == current_quarter)
            ]
            if not current_q_data.empty:
                current_quarter_dividend = current_q_data['dividend'].iloc[0]
            else:
                # If no current quarter data yet, try to get the most recent quarterly dividend
                quarterly_stats_sorted = quarterly_stats.sort_values(['year', 'quarter'], ascending=False)
                if not quarterly_stats_sorted.empty:
                    latest_quarter_data = quarterly_stats_sorted.iloc[0]
                    # Only use it if it's from last year or more recent
                    if latest_quarter_data['year'] >= current_year - 1:
                        current_quarter_dividend = latest_quarter_data['dividend']
        
        # Calculate growth rates
        dividend_growth = annual_dividends.pct_change().dropna() * 100
        
        # Calculate statistics
        total_years = len(annual_dividends)
        avg_annual_dividend = annual_dividends.mean()
        current_annual_dividend = annual_dividends.iloc[-1] if len(annual_dividends) > 0 else 0
        
        # Calculate compound annual growth rate (CAGR)
        if len(annual_dividends) >= 2:
            first_dividend = annual_dividends.iloc[0]
            last_dividend = annual_dividends.iloc[-1]
            years_span = len(annual_dividends) - 1
            cagr = ((last_dividend / first_dividend) ** (1/years_span) - 1) * 100 if first_dividend > 0 else 0
        else:
            cagr = 0
        
        # Calculate consistency metrics
        positive_growth_years = (dividend_growth > 0).sum()
        consistency_rate = (positive_growth_years / len(dividend_growth) * 100) if len(dividend_growth) > 0 else 0
        
        # Calculate volatility of dividend growth
        growth_volatility = dividend_growth.std() if len(dividend_growth) > 1 else 0
        
        # Recent performance (last 5 years)
        recent_dividends = annual_dividends.tail(5)
        if len(recent_dividends) >= 2:
            recent_growth = recent_dividends.pct_change().dropna() * 100
            recent_avg_growth = recent_growth.mean()
        else:
            recent_avg_growth = 0
        
        return {
            'total_payments': len(dividends),
            'years_of_payments': total_years,
            'first_payment_date': dividends.index[0].strftime('%Y-%m-%d'),
            'last_payment_date': dividends.index[-1].strftime('%Y-%m-%d'),
            'current_annual_dividend': current_annual_dividend,
            'avg_annual_dividend': avg_annual_dividend,
            'dividend_cagr': cagr,
            'consistency_rate': consistency_rate,
            'growth_volatility': growth_volatility,
            'recent_avg_growth': recent_avg_growth,
            'annual_dividends': annual_dividends.to_dict(),
            'quarterly_stats': quarterly_stats.to_dict('records'),
            'dividend_growth_rates': dividend_growth.to_dict(),
            'total_dividend_paid': dividends.sum(),
            'avg_quarterly_dividend': dividends.mean(),
            'max_annual_dividend': annual_dividends.max(),
            'min_annual_dividend': annual_dividends.min(),
            'current_quarter_dividend': current_quarter_dividend
        }
    
    except Exception as e:
        print(f"Error getting dividend history for {symbol}: {str(e)}")
        return None

def display_single_stock_analysis(symbol, include_sentiment=False):
    """Display comprehensive analysis for a single stock"""
    print("🔍" + "="*80)
    print(f"COMPREHENSIVE STOCK ANALYSIS: {symbol.upper()}")
    print("🔍" + "="*80)
    
    try:
        # Get stock data
        stock = yf.Ticker(symbol)
        info = stock.info
        
        # Check if stock data is valid
        if not info or info.get('regularMarketPrice') is None:
            print(f"\n❌ ERROR: No data found for symbol '{symbol}'")
            print(f"\n💡 Troubleshooting tips:")
            print(f"   • Verify the stock symbol is correct")
            print(f"   • Check your internet connection")
            print(f"   • Try again in a few moments")
            print(f"\n   Examples of valid symbols: KO, AAPL, MSFT, JNJ, PEP\n")
            return False
        
        # Basic information
        company_name = info.get('longName', info.get('shortName', 'N/A'))
        sector = info.get('sector', 'N/A')
        industry = info.get('industry', 'N/A')
        
        print(f"\n📊 COMPANY OVERVIEW")
        print("-" * 50)
        print(f"Company:     {company_name}")
        print(f"Sector:      {sector}")
        print(f"Industry:    {industry}")
        print(f"Symbol:      {symbol.upper()}")
        
        # Current price and dividend info
        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        dividend_rate = info.get('dividendRate', 0)
        dividend_yield = info.get('dividendYield', 0)
        
        # Ex-dividend date
        ex_dividend_date = info.get('exDividendDate', None)
        ex_date = datetime.fromtimestamp(ex_dividend_date).strftime('%Y-%m-%d') if ex_dividend_date else 'N/A'
        
        print(f"\n💰 CURRENT DIVIDEND INFORMATION")
        print("-" * 50)
        print(f"Current Price:      ${current_price:.2f}")
        print(f"Dividend Rate:      ${dividend_rate:.2f}" if dividend_rate else "Dividend Rate:      No dividend")
        print(f"Dividend Yield:     {dividend_yield:.2f}%" if dividend_yield else "Dividend Yield:     No dividend")
        print(f"Ex-Dividend Date:   {ex_date}")
        
        # Special note for non-dividend stocks
        if not dividend_rate or dividend_rate == 0:
            print(f"\n💡 Note: This stock does not currently pay dividends.")
            print(f"   Analysis will focus on growth and valuation metrics.")
        
        # Get comprehensive dividend history (if any)
        dividend_history = get_comprehensive_dividend_history(stock, symbol)
        
        if dividend_history:
            print(f"\n📈 DIVIDEND HISTORY & STATISTICS")
            print("-" * 50)
            print(f"Years of Payments:        {dividend_history['years_of_payments']}")
            print(f"Total Payments:           {dividend_history['total_payments']}")
            print(f"First Payment:            {dividend_history['first_payment_date']}")
            print(f"Last Payment:             {dividend_history['last_payment_date']}")
            print(f"Current Annual Dividend:  ${dividend_history['current_annual_dividend']:.2f}")
            print(f"Average Annual Dividend:  ${dividend_history['avg_annual_dividend']:.2f}")
            print(f"Total Dividends Paid:     ${dividend_history['total_dividend_paid']:.2f}")
            
            # Display current quarter dividend information
            from datetime import date
            today = date.today()
            current_q = (today.month - 1) // 3 + 1
            current_quarter_div = dividend_history.get('current_quarter_dividend')
            if current_quarter_div:
                print(f"Current Quarter Dividend: ${current_quarter_div:.2f} (Q{current_q} {today.year})")
            else:
                print(f"Current Quarter Dividend: Not yet available (Q{current_q} {today.year})")
            
            print(f"\n📊 DIVIDEND GROWTH ANALYSIS")
            print("-" * 50)
            print(f"Dividend CAGR:            {dividend_history['dividend_cagr']:+.2f}%")
            print(f"Consistency Rate:         {dividend_history['consistency_rate']:.1f}%")
            print(f"Growth Volatility:        {dividend_history['growth_volatility']:.2f}%")
            print(f"Recent Avg Growth (5Y):   {dividend_history['recent_avg_growth']:+.2f}%")
            print(f"Max Annual Dividend:      ${dividend_history['max_annual_dividend']:.2f}")
            print(f"Min Annual Dividend:      ${dividend_history['min_annual_dividend']:.2f}")
            
            # Display annual dividend history (last 10 years)
            print(f"\n📅 ANNUAL DIVIDEND HISTORY (Last 10 Years)")
            print("-" * 50)
            annual_divs = dividend_history['annual_dividends']
            growth_rates = dividend_history['dividend_growth_rates']
            
            print(f"{'Year':<6} | {'Dividend':<10} | {'Growth':<10}")
            print("-" * 30)
            
            # Show last 10 years
            recent_years = sorted(annual_divs.keys())[-10:]
            for year in recent_years:
                dividend = annual_divs[year]
                growth = growth_rates.get(year, 0)
                growth_str = f"{growth:+.1f}%" if growth != 0 else "N/A"
                print(f"{year:<6} | ${dividend:<9.2f} | {growth_str:<10}")
            
            # Display quarterly dividend history (last 8 quarters)
            print(f"\n📊 QUARTERLY DIVIDEND HISTORY (Last 8 Quarters)")
            print("-" * 50)
            quarterly_stats = dividend_history.get('quarterly_stats', [])
            if quarterly_stats:
                # Sort by year and quarter, get last 8 quarters
                sorted_quarters = sorted(quarterly_stats, key=lambda x: (x['year'], x['quarter']))
                recent_quarters = sorted_quarters[-8:]
                
                print(f"{'Quarter':<10} | {'Dividend':<10}")
                print("-" * 22)
                
                for quarter_data in recent_quarters:
                    year = quarter_data['year']
                    quarter = quarter_data['quarter']
                    dividend = quarter_data['dividend']
                    
                    # Mark current quarter
                    marker = " ← Current" if year == today.year and quarter == current_q else ""
                    quarter_str = f"{year} Q{quarter}"
                    print(f"{quarter_str:<10} | ${dividend:<9.2f}{marker}")
            else:
                print("No quarterly data available")
                
        else:
            print(f"\n📈 DIVIDEND HISTORY")
            print("-" * 50)
            print(f"No dividend payment history found for {symbol.upper()}")
            print(f"This may be a growth stock focused on capital appreciation.")
        
        # Get fundamental metrics
        market_cap = info.get('marketCap', 0)
        trailing_pe = info.get('trailingPE', None)
        forward_pe = info.get('forwardPE', None)
        peg_ratio = info.get('pegRatio', None)
        price_to_book = info.get('priceToBook', None)
        debt_to_equity = info.get('debtToEquity', None)
        current_ratio = info.get('currentRatio', None)
        ev_ebitda = info.get('enterpriseToEbitda', None)
        
        print(f"\n🏢 FUNDAMENTAL ANALYSIS")
        print("-" * 50)
        print(f"Market Cap:           ${market_cap/1e9:.1f}B" if market_cap else "Market Cap:           N/A")
        print(f"Trailing P/E:         {trailing_pe:.2f}" if trailing_pe else "Trailing P/E:         N/A")
        print(f"Forward P/E:          {forward_pe:.2f}" if forward_pe else "Forward P/E:          N/A")
        print(f"PEG Ratio:            {peg_ratio:.2f}" if peg_ratio else "PEG Ratio:            N/A")
        print(f"Price to Book:        {price_to_book:.2f}" if price_to_book else "Price to Book:        N/A")
        print(f"Debt to Equity:       {debt_to_equity:.2f}" if debt_to_equity else "Debt to Equity:       N/A")
        print(f"Current Ratio:        {current_ratio:.2f}" if current_ratio else "Current Ratio:        N/A")
        print(f"EV/EBITDA:           {ev_ebitda:.2f}" if ev_ebitda else "EV/EBITDA:           N/A")
        
        # Get historical performance
        historical_data = get_historical_data(stock, symbol)
        
        if historical_data:
            print(f"\n📈 HISTORICAL PERFORMANCE")
            print("-" * 50)
            print(f"1-Year Return:        {historical_data.get('price_1y_return', 0):+.1f}%" if historical_data.get('price_1y_return') else "1-Year Return:        N/A")
            print(f"3-Year Return:        {historical_data.get('price_3y_return', 0):+.1f}%" if historical_data.get('price_3y_return') else "3-Year Return:        N/A")
            print(f"5-Year Return:        {historical_data.get('price_5y_return', 0):+.1f}%" if historical_data.get('price_5y_return') else "5-Year Return:        N/A")
            print(f"1-Year Volatility:    {historical_data.get('volatility_1y', 0):.1f}%" if historical_data.get('volatility_1y') else "1-Year Volatility:    N/A")
            print(f"Max Drawdown:         {historical_data.get('max_drawdown', 0):.1f}%" if historical_data.get('max_drawdown') else "Max Drawdown:         N/A")
            print(f"52W High:             ${historical_data.get('price_52w_high', 0):.2f}" if historical_data.get('price_52w_high') else "52W High:             N/A")
            print(f"52W Low:              ${historical_data.get('price_52w_low', 0):.2f}" if historical_data.get('price_52w_low') else "52W Low:              N/A")
            print(f"% of 52W High:        {historical_data.get('price_vs_52w_high', 0):+.1f}%" if historical_data.get('price_vs_52w_high') else "% of 52W High:        N/A")
        
        # Strategic analysis
        strategy, score_percentage, strategy_details = strategic_analysis(
            stock, symbol, market_cap, trailing_pe, dividend_yield, debt_to_equity, ev_ebitda, current_ratio
        )
        
        print(f"\n🎯 STRATEGIC RECOMMENDATION")
        print("-" * 50)
        print(f"Recommendation:       {strategy}")
        print(f"Strategic Score:      {score_percentage:.0f}%")
        print(f"\nKey Factors:")
        for detail in strategy_details[:8]:  # Show top 8 factors
            print(f"• {detail}")
        
        # Valuation assessment
        valuation = comprehensive_valuation_assessment(trailing_pe, forward_pe, peg_ratio, None, price_to_book, ev_ebitda)
        print(f"\nValuation Assessment: {valuation}")
        
        # Sentiment analysis (if requested)
        if include_sentiment and SENTIMENT_AVAILABLE:
            print(f"\n📰 SENTIMENT ANALYSIS")
            print("-" * 50)
            
            # Initialize sentiment classifier for single analysis
            try:
                print("🤖 Initializing sentiment analysis model...")
                sentiment_classifier = pipeline(
                    "sentiment-analysis",
                    model="distilbert-base-uncased-finetuned-sst-2-english",
                    tokenizer="distilbert-base-uncased-finetuned-sst-2-english"
                )
                print("✅ Model initialized, analyzing sentiment...")
                
                sentiment_score, sentiment_confidence, news_count = analyze_news_sentiment(symbol, DEFAULT_NEWS_DAYS, verbose=True, sentiment_classifier=sentiment_classifier)
            except Exception as e:
                print(f"❌ Error initializing sentiment model: {e}")
                sentiment_score, sentiment_confidence, news_count = 0, 0, 0
            
            if news_count > 0:
                sentiment_label = "Very Positive" if sentiment_score > 0.6 else \
                                 "Positive" if sentiment_score > 0.2 else \
                                 "Neutral" if abs(sentiment_score) <= 0.2 else \
                                 "Negative" if sentiment_score > -0.6 else \
                                 "Very Negative"
                
                confidence_label = "Very High" if sentiment_confidence > 0.9 else \
                                  "High" if sentiment_confidence > 0.8 else \
                                  "Moderate" if sentiment_confidence > 0.6 else \
                                  "Low"
                
                print(f"Sentiment Score:       {sentiment_score:+.3f} ({sentiment_label})")
                print(f"Confidence Level:      {sentiment_confidence:.3f} ({confidence_label})")
                print(f"Articles Analyzed:     {news_count}")
                print(f"Analysis Period:       Last {DEFAULT_NEWS_DAYS} days")
                
                # Sentiment interpretation
                if sentiment_score > 0.2:
                    print(f"📈 Market sentiment appears positive for {symbol}")
                elif sentiment_score < -0.2:
                    print(f"📉 Market sentiment appears negative for {symbol}")
                else:
                    print(f"⚖️  Market sentiment appears neutral for {symbol}")
            else:
                print(f"No recent news found for sentiment analysis")
        elif include_sentiment and not SENTIMENT_AVAILABLE:
            print(f"\n📰 SENTIMENT ANALYSIS")
            print("-" * 50)
            print(f"⚠️  Sentiment analysis libraries not available")
            print(f"   Install with: pip install transformers torch feedparser requests beautifulsoup4")
        
        # Summary and conclusion
        print(f"\n📋 INVESTMENT SUMMARY")
        print("=" * 50)
        
        if dividend_history:
            consistency = "Excellent" if dividend_history['consistency_rate'] > 80 else \
                         "Good" if dividend_history['consistency_rate'] > 60 else \
                         "Moderate" if dividend_history['consistency_rate'] > 40 else "Poor"
            
            print(f"Dividend Consistency:  {consistency} ({dividend_history['consistency_rate']:.1f}%)")
            print(f"Dividend Growth:       {dividend_history['dividend_cagr']:+.1f}% CAGR")
        else:
            print(f"Dividend Status:       No current dividend payments")
            print(f"Investment Focus:      Growth/Capital appreciation")
        
        print(f"Current Valuation:     {valuation}")
        print(f"Strategic Rating:      {strategy} ({score_percentage:.0f}%)")
        
        # Risk assessment
        risk_factors = []
        if debt_to_equity and debt_to_equity > 1.0:
            risk_factors.append("High debt levels")
        if current_ratio and current_ratio < 1.0:
            risk_factors.append("Liquidity concerns")
        if dividend_yield and dividend_yield > 0.08:
            risk_factors.append("Unusually high yield (sustainability risk)")
        if not dividend_rate or dividend_rate == 0:
            risk_factors.append("No dividend income (growth stock risk)")
        
        if risk_factors:
            print(f"\n⚠️  Risk Factors:")
            for risk in risk_factors:
                print(f"• {risk}")
        else:
            print(f"\n✅ No major risk factors identified")
        
        print(f"\n" + "="*80)
        print("Analysis completed successfully!")
        print("="*80)
        
    except Exception as e:
        print(f"❌ Error analyzing {symbol}: {str(e)}")
        print(f"💡 This could be due to:")
        print(f"   • Invalid stock symbol")
        print(f"   • Network connectivity issues")
        print(f"   • Temporary data provider issues")
        print(f"   • Delisted or inactive stock")
        return False
    
    return True

def run_full_analysis(include_sentiment=False):
    """Run the full dividend kings analysis for all stocks"""
    
    # Initialize sentiment classifier once if needed
    sentiment_classifier = None
    if include_sentiment and SENTIMENT_AVAILABLE:
        print("🤖 Initializing sentiment analysis model...")
        try:
            sentiment_classifier = pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sst-2-english",
                tokenizer="distilbert-base-uncased-finetuned-sst-2-english"
            )
            print("✅ Sentiment analysis model initialized")
        except Exception as e:
            print(f"❌ Failed to initialize sentiment model: {e}")
            include_sentiment = False
    
    # List of dividend kings
    symbols = [
        'ABBV', 'ADM', 'ADP', 'AFG', 'AMAT', 'AMT', 'ARCC', 'ARE', 'AWK', 'BAC', 'BBY', 
        'BEN', 'BMY', 'BTI', 'CMCSA', 'CSCO', 'DVN', 'ESS', 'HSY', 'IBM', 'JNJ', 
        'KO', 'MDLZ', 'MDT', 'MMM', 'MO', 'NEE', 'NKE', 'NNN', 'NSP', 'O', 'PEP', 
        'PRU', 'QCOM', 'SBUX', 'SWK', 'SWKS', 'T', 'TROW', 'UGI', 'VSNT', 'VZ', 'WPC', 'XOM', 'ZTS'
    ]
    
    # Store results for strategy ranking
    strategy_results = []
    csv_data = []

    # Fetch data and print results
    print("\n" + "="*200)
    print("COMPREHENSIVE DIVIDEND KINGS FINANCIAL ANALYSIS")
    print("="*200)
    print(f"{'Stock':<6} | {'Div Rate':<8} | {'Yield':<6} | {'Ex-Date':<12} | {'Price':<8} | {'1Y Ret':<7} | {'P/E':<6} | {'EV/EBITDA':<9} | {'Strategy':<14} | {'Score':<6}")
    print('-'*200)

    for symbol in symbols:
        try:
            print(f"📊 Processing {symbol}...", end=" ")
            
            # Add small delay to avoid rate limiting
            import time
            time.sleep(0.5)
            
            stock = yf.Ticker(symbol)
            info = stock.info

            # Get dividend information
            dividend = info.get('dividendRate', 0)
            dy = info.get('dividendYield', None)
            ex_date = info.get('exDividendDate', None)
            
            # Get recent dividend date from dividend history
            try:
                dividends = stock.dividends
                if not dividends.empty:
                    recent_dividend_date = dividends.index[-1]
                else:
                    recent_dividend_date = None
            except:
                recent_dividend_date = None

            # Get current price
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            
            # Get comprehensive financial metrics
            market_cap = info.get('marketCap', None)
            enterprise_value = info.get('enterpriseValue', None)
            trailing_pe = info.get('trailingPE', None)
            forward_pe = info.get('forwardPE', None)
            peg_ratio = info.get('pegRatio', None)
            price_to_sales = info.get('priceToSalesTrailing12Months', None)
            price_to_book = info.get('priceToBook', None)
            ev_revenue = info.get('enterpriseToRevenue', None)
            ev_ebitda = info.get('enterpriseToEbitda', None)
            debt_to_equity = info.get('debtToEquity', None)
            current_ratio = info.get('currentRatio', None)
            
            # Get comprehensive historical data
            historical_data = get_historical_data(stock, symbol)
            
            # Get comprehensive dividend history for enhanced metrics
            dividend_history = get_comprehensive_dividend_history(stock, symbol)
            
            # Calculate additional dividend metrics (including 2025)
            dividend_growth_rate = None
            dividend_consistency = None
            years_of_payments = None
            
            if dividend_history:
                annual_divs = dividend_history['annual_dividends']
                # Include all available data including 2025
                filtered_divs = annual_divs
                
                if len(filtered_divs) >= 2:
                    years = sorted(filtered_divs.keys())
                    first_div = filtered_divs[years[0]]
                    last_div = filtered_divs[years[-1]]
                    years_span = len(years) - 1
                    
                    if first_div > 0 and years_span > 0:
                        dividend_growth_rate = ((last_div / first_div) ** (1/years_span) - 1) * 100
                
                dividend_consistency = dividend_history.get('consistency_rate')
                years_of_payments = dividend_history.get('years_of_payments')
            
            # Get additional financial metrics
            payout_ratio = info.get('payoutRatio', None)
            free_cash_flow = info.get('freeCashflow', None)
            total_cash = info.get('totalCash', None)
            operating_cash_flow = info.get('operatingCashflow', None)
            
            # Calculate FCF yield
            fcf_yield = None
            if free_cash_flow is not None and market_cap is not None and market_cap > 0:
                fcf_yield = (free_cash_flow / market_cap) * 100
            
            # Calculate cash to market cap ratio
            cash_to_market_cap = None
            if total_cash is not None and market_cap is not None and market_cap > 0:
                cash_to_market_cap = (total_cash / market_cap) * 100
            
            # Get comprehensive assessment
            valuation_assessment = comprehensive_valuation_assessment(trailing_pe, forward_pe, peg_ratio, price_to_sales, price_to_book, ev_ebitda)
            
            # Get strategic analysis based on prioritized metrics
            strategy, score_percentage, strategy_details = strategic_analysis(
                stock, symbol, market_cap, trailing_pe, dy, debt_to_equity, ev_ebitda, current_ratio
            )

            # Get sentiment analysis (for CSV only, not affecting strategy)
            if include_sentiment and SENTIMENT_AVAILABLE and sentiment_classifier is not None:
                sentiment_score, sentiment_confidence, news_count = analyze_news_sentiment(symbol, DEFAULT_NEWS_DAYS, verbose=False, sentiment_classifier=sentiment_classifier)
            else:
                sentiment_score, sentiment_confidence, news_count = 0, 0, 0

            # Format values for display
            dividend_formatted = f"${dividend:.2f}" if dividend else "N/A"
            dy_str = f"{dy:.2f}%" if dy else "N/A"
            
            # Format dates
            if ex_date:
                ex_date_str = datetime.fromtimestamp(ex_date).strftime('%Y-%m-%d')
            else:
                ex_date_str = "N/A"
            
            if recent_dividend_date:
                recent_div_date_str = recent_dividend_date.strftime('%Y-%m-%d')
            else:
                recent_div_date_str = "N/A"
            
            # Format other metrics
            price_str = f"${current_price:.2f}" if current_price else "N/A"
            ret_1y_str = f"{historical_data.get('price_1y_return', 0):+.1f}%" if historical_data.get('price_1y_return') else "N/A"
            trailing_pe_str = f"{trailing_pe:.2f}" if trailing_pe else "N/A"
            ev_ebitda_str = f"{ev_ebitda:.2f}" if ev_ebitda else "N/A"
            score_str = f"{score_percentage:.0f}%"

            print(f"✅")
            print(f"{symbol:<6} | {dividend_formatted:<8} | {dy_str:<6} | {ex_date_str:<12} | {price_str:<8} | {ret_1y_str:<7} | {trailing_pe_str:<6} | {ev_ebitda_str:<9} | {strategy:<14} | {score_str:<6}")

            # Store for strategy ranking
            strategy_results.append({
                'symbol': symbol,
                'strategy': strategy,
                'score': score_percentage,
                'details': strategy_details
            })

            # Store comprehensive data for CSV export
            csv_data.append({
                'Symbol': symbol,
                'Dividend_Rate': dividend,
                'Dividend_Yield_Percent': dy if dy else None,
                'Dividend_Growth_Rate_CAGR': dividend_growth_rate,
                'Dividend_Consistency_Percent': dividend_consistency,
                'Years_of_Dividend_Payments': years_of_payments,
                'Payout_Ratio_Percent': payout_ratio * 100 if payout_ratio else None,
                'Free_Cash_Flow_Billions': free_cash_flow / 1e9 if free_cash_flow else None,
                'FCF_Yield_Percent': fcf_yield,
                'Cash_to_MarketCap_Percent': cash_to_market_cap,
                'Operating_Cash_Flow_Billions': operating_cash_flow / 1e9 if operating_cash_flow else None,
                'Current_Price': current_price,
                'Ex_Dividend_Date': ex_date_str,
                'Recent_Dividend_Date': recent_div_date_str,
                'Current_Quarter_Dividend': dividend_history.get('current_quarter_dividend') if dividend_history else None,
                
                # Historical Performance
                'Price_Return_1Y_Percent': historical_data.get('price_1y_return'),
                'Price_Return_3Y_Percent': historical_data.get('price_3y_return'),
                'Price_Return_5Y_Percent': historical_data.get('price_5y_return'),
                'Volatility_1Y_Percent': historical_data.get('volatility_1y'),
                'Max_Drawdown_Percent': historical_data.get('max_drawdown'),
                'Price_vs_52W_High_Percent': historical_data.get('price_vs_52w_high'),
                'Price_52W_High': historical_data.get('price_52w_high'),
                'Price_52W_Low': historical_data.get('price_52w_low'),
                
                # Current Fundamentals
                'Market_Cap_Billions': market_cap/1e9 if market_cap else None,
                'Enterprise_Value_Billions': enterprise_value/1e9 if enterprise_value else None,
                'Trailing_PE': trailing_pe,
                'Forward_PE': forward_pe,
                'PEG_Ratio': peg_ratio,
                'Price_to_Sales': price_to_sales,
                'Price_to_Book': price_to_book,
                'EV_to_Revenue': ev_revenue,
                'EV_to_EBITDA': ev_ebitda,
                'Current_Ratio': current_ratio,
                'Debt_to_Equity': debt_to_equity,
                
                # Assessment
                'Valuation_Assessment': valuation_assessment,
                'Strategic_Recommendation': strategy,
                'Strategic_Score_Percent': score_percentage,
                
                # Sentiment Analysis (for information only, not used in strategy)
                'Sentiment_Score': sentiment_score,
                'Sentiment_Confidence': sentiment_confidence,
                'News_Articles_Count': news_count
            })

        except Exception as e:
            print(f"❌ ({str(e)[:30]})")
            print(f"{symbol:<6} | N/A      | N/A    | N/A          | N/A      | N/A     | N/A    | N/A       | Error          | 0%")
            strategy_results.append({
                'symbol': symbol,
                'strategy': 'ERROR',
                'score': 0,
                'details': ['Unable to retrieve data']
            })
            
            # Store error data for CSV
            csv_data.append({
                'Symbol': symbol,
                'Dividend_Rate': None,
                'Dividend_Yield_Percent': None,
                'Dividend_Growth_Rate_CAGR': None,
                'Dividend_Consistency_Percent': None,
                'Years_of_Dividend_Payments': None,
                'Payout_Ratio_Percent': None,
                'Free_Cash_Flow_Billions': None,
                'FCF_Yield_Percent': None,
                'Cash_to_MarketCap_Percent': None,
                'Operating_Cash_Flow_Billions': None,
                'Current_Price': None,
                'Ex_Dividend_Date': 'N/A',
                'Recent_Dividend_Date': 'N/A',
                'Current_Quarter_Dividend': None,
                'Price_Return_1Y_Percent': None,
                'Price_Return_3Y_Percent': None,
                'Price_Return_5Y_Percent': None,
                'Volatility_1Y_Percent': None,
                'Max_Drawdown_Percent': None,
                'Price_vs_52W_High_Percent': None,
                'Price_52W_High': None,
                'Price_52W_Low': None,
                'Market_Cap_Billions': None,
                'Enterprise_Value_Billions': None,
                'Trailing_PE': None,
                'Forward_PE': None,
                'PEG_Ratio': None,
                'Price_to_Sales': None,
                'Price_to_Book': None,
                'EV_to_Revenue': None,
                'EV_to_EBITDA': None,
                'Current_Ratio': None,
                'Debt_to_Equity': None,
                'Valuation_Assessment': 'Error',
                'Strategic_Recommendation': 'ERROR',
                'Strategic_Score_Percent': 0,
                
                # Sentiment Analysis (error case)
                'Sentiment_Score': None,
                'Sentiment_Confidence': None,
                'News_Articles_Count': 0
            })

    # Sort results by strategy score for ranking
    strategy_results.sort(key=lambda x: x['score'], reverse=True)

    # Display strategic recommendations
    print("\n" + "="*200)
    print("STRATEGIC INVESTMENT RECOMMENDATIONS")
    print("="*200)
    print("Ranked by Strategic Score (Based on Dividend Yield, Growth Rate, Payout Ratio, FCF, Earnings Stability, Debt Levels, Coverage Ratios, Cash Reserves)")
    print()

    print("TOP STRATEGIC PICKS:")
    print("-" * 50)
    for i, result in enumerate(strategy_results[:10], 1):
        print(f"{i:2d}. {result['symbol']:<6} - {result['strategy']:<14} (Score: {result['score']:.0f}%)")

    print("\nTOP 5 DETAILED ANALYSIS:")
    print("-" * 80)
    for i, result in enumerate(strategy_results[:5], 1):
        print(f"\n{i}. {result['symbol']} - {result['strategy']} (Score: {result['score']:.0f}%)")
        print("   Key Factors:")
        for detail in result['details'][:6]:  # Show top 6 factors
            print(f"   • {detail}")

    print("\nSTRATEGY CATEGORIES:")
    buy_stocks = [r for r in strategy_results if r['strategy'] == 'BUY']
    strong_consider = [r for r in strategy_results if r['strategy'] == 'STRONG CONSIDER']
    consider = [r for r in strategy_results if r['strategy'] == 'CONSIDER']
    hold_watch = [r for r in strategy_results if r['strategy'] == 'HOLD/WATCH']
    avoid = [r for r in strategy_results if r['strategy'] == 'AVOID']

    if buy_stocks:
        print(f"\nBUY ({len(buy_stocks)} stocks): {', '.join([s['symbol'] for s in buy_stocks])}")
    if strong_consider:
        print(f"STRONG CONSIDER ({len(strong_consider)} stocks): {', '.join([s['symbol'] for s in strong_consider])}")
    if consider:
        print(f"CONSIDER ({len(consider)} stocks): {', '.join([s['symbol'] for s in consider])}")
    if hold_watch:
        print(f"HOLD/WATCH ({len(hold_watch)} stocks): {', '.join([s['symbol'] for s in hold_watch])}")
    if avoid:
        print(f"AVOID ({len(avoid)} stocks): {', '.join([s['symbol'] for s in avoid])}")

    # Generate CSV report
    print("\n" + "="*200)
    print("GENERATING CSV REPORT...")
    print("="*200)

    # Create reports folder if it doesn't exist
    reports_folder = "reports"
    if not os.path.exists(reports_folder):
        os.makedirs(reports_folder)
        print(f"Created '{reports_folder}' folder")

    # Generate timestamp for filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{reports_folder}/dividend_kings_analysis_{timestamp}.csv"

    # Write CSV file
    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            if csv_data:
                fieldnames = csv_data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Write header
                writer.writeheader()
                
                # Sort CSV data by strategic score (highest first)
                csv_data_sorted = sorted(csv_data, key=lambda x: x['Strategic_Score_Percent'] or 0, reverse=True)
                
                # Write data rows
                for row in csv_data_sorted:
                    writer.writerow(row)
        
        print(f"✅ CSV report successfully generated: {csv_filename}")
        print(f"📊 Report contains {len(csv_data)} dividend kings with enhanced dividend analysis")
        print(f"📅 Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 Dividend analysis includes all available data (including 2025)")
        
        print(f"\n📈 New Dividend-Focused Metrics Included:")
        print(f"   • Dividend_Growth_Rate_CAGR: Annual compound growth rate (all available years)")
        print(f"   • Dividend_Consistency_Percent: Percentage of years with dividend increases")
        print(f"   • Payout_Ratio_Percent: Percentage of earnings paid as dividends")
        print(f"   • FCF_Yield_Percent: Free cash flow as percentage of market cap")
        print(f"   • Cash_to_MarketCap_Percent: Cash reserves relative to market capitalization")
        print(f"   • Operating_Cash_Flow_Billions: Annual operating cash flow generation")
        
        if include_sentiment and SENTIMENT_AVAILABLE:
            print(f"📰 Sentiment analysis included (columns: Sentiment_Score, Sentiment_Confidence, News_Articles_Count)")
            print(f"   • Sentiment_Score: -1.0 (very negative) to +1.0 (very positive)")
            print(f"   • Sentiment_Confidence: 0.0 to 1.0 (confidence in sentiment classification)")
            print(f"   • News_Articles_Count: Number of news articles analyzed")
        
        # Display file info
        file_size = os.path.getsize(csv_filename)
        print(f"📁 File size: {file_size:,} bytes")
        
        # Show top 5 from CSV
        print(f"\n🏆 TOP 5 STRATEGIC PICKS (from CSV):")
        for i, row in enumerate(csv_data_sorted[:5], 1):
            score = row['Strategic_Score_Percent'] or 0
            print(f"{i}. {row['Symbol']} - {row['Strategic_Recommendation']} (Score: {score:.0f}%)")
            
    except Exception as e:
        print(f"❌ Error generating CSV report: {str(e)}")

    print(f"\n💾 CSV Report Location: {os.path.abspath(csv_filename)}")
    print("🔍 Open this file in Excel, Google Sheets, or any spreadsheet application for detailed analysis.")

    print("\n" + "="*200)
    print("ANALYSIS COMPLETE!")
    print("="*200)

def main():
    """Main function with command-line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Comprehensive Dividend Kings Analysis Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  %(prog)s                                    Analyze all dividend kings
  %(prog)s --sentiment                        Include sentiment analysis
  %(prog)s --stock KO                         Analyze Coca-Cola
  %(prog)s --stock UPS --sentiment            Analyze UPS with sentiment
  %(prog)s --list                             Show dividend kings list

ABOUT DIVIDEND KINGS:
  Companies with 25+ years of consecutive dividend increases.
  This tool can analyze any publicly traded stock, not just dividend kings.

ANALYSIS FEATURES:
  • Current dividend metrics and payment dates
  • Complete dividend payment history and statistics
  • Fundamental valuation metrics (P/E, P/B, EV/EBITDA)
  • Strategic investment recommendations with scoring
  • Risk assessment and sustainability analysis
  • Optional sentiment analysis (requires --sentiment flag)
        """)
    
    parser.add_argument('--stock', '-s', 
                       help='Analyze any stock symbol (e.g., KO, UPS, AAPL, MSFT)')
    
    parser.add_argument('--list', '-l', action='store_true',
                       help='List all dividend kings symbols (25+ years consecutive increases)')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output with detailed analysis')
    
    parser.add_argument('--sentiment', action='store_true',
                       help='Include sentiment analysis in the report (requires transformers and feedparser)')
    
    args = parser.parse_args()
    
    # List of dividend kings
    dividend_kings = [
        'ABBV', 'ADM', 'ADP','AFG', 'AMAT', 'AMT', 'ARCC', 'ARE', 'AWK', 'BAC', 'BBY', 
        'BEN', 'BMY', 'BTI', 'CMCSA', 'CSCO', 'DVN', 'ESS', 'HSY', 'IBM', 'JNJ', 
        'KO', 'MDLZ', 'MDT', 'MMM', 'MO', 'NEE', 'NKE', 'NNN', 'NSP', 'O', 'PEP', 
        'PRU', 'QCOM', 'SBUX', 'SWK', 'SWKS', 'T', 'TROW', 'UGI', 'VSNT', 'VZ', 'WPC', 'XOM', 'ZTS'
    ]
    
    # Handle --list option
    if args.list:
        print("\n📊 DIVIDEND KINGS - 44 COMPANIES")
        print("=" * 70)
        print("Companies with 25+ years of consecutive dividend increases:\n")
        
        # Display in organized format (8 per row)
        for i in range(0, len(dividend_kings), 8):
            row = dividend_kings[i:i+8]
            print("  " + "  ".join(f"{s:<6}" for s in row))
        
        print(f"\n💡 USAGE EXAMPLES:")
        print(f"   python {os.path.basename(__file__)} --stock KO")
        print(f"   python {os.path.basename(__file__)} --stock UPS --sentiment")
        print(f"   python {os.path.basename(__file__)} --sentiment")
        print(f"\n   You can analyze ANY stock symbol, not just dividend kings!\n")
        return
    
    # Handle single stock analysis
    if args.stock:
        symbol = args.stock.upper()
        
        # Check if it's a dividend king
        is_dividend_king = symbol in dividend_kings
        
        if is_dividend_king:
            print(f"🎯 Analyzing dividend king: {symbol}")
        else:
            print(f"🎯 Analyzing stock: {symbol} (not a dividend king)")
            print(f"💡 Note: This stock is not in the dividend kings list.")
            print(f"   Dividend kings have 25+ years of consecutive dividend increases.")
            print()
        
        # Run single stock analysis (works for any stock)
        success = display_single_stock_analysis(symbol, include_sentiment=args.sentiment)
        
        if not success:
            print(f"❌ Failed to analyze {symbol}")
            print(f"💡 Make sure the stock symbol is valid and try again.")
            sys.exit(1)
        
        return
    
    # Default: Run full analysis for all dividend kings
    print("🏆 Running comprehensive analysis for all dividend kings...")
    if args.sentiment and SENTIMENT_AVAILABLE:
        print("📰 Including sentiment analysis...")
    elif args.sentiment and not SENTIMENT_AVAILABLE:
        print("⚠️  Sentiment analysis requested but libraries not available")
    print("⏱️  This will take 5-10 minutes to complete...")
    print()
    run_full_analysis(include_sentiment=args.sentiment)

if __name__ == "__main__":
    main()