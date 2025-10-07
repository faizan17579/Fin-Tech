from __future__ import annotations

import random
import urllib.parse
from bs4 import BeautifulSoup  # noqa: F401  # kept for future HTML cleaning
import yfinance as yf
import feedparser
import requests
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import email.utils
import json
import re
from typing import Dict, List, Optional, Tuple


class FinTechDataCurator:
    def __init__(self) -> None:
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        self.session = requests.Session()
        self._setup_session()

    def _setup_session(self) -> None:
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })

    def collect_comprehensive_data(self, exchange: str, symbol: str, days_history: int = 7) -> Dict:
        asset_type = 'crypto' if exchange.upper() == 'CRYPTO' else 'stocks'
        structured_data = self._collect_structured_data_safe(symbol, days_history)
        news_data = self._scrape_news_data_multi_source(symbol, asset_type, days_history)
        combined_data = self._align_data_by_date(structured_data, news_data)
        dataset = {
            'metadata': {
                'symbol': symbol,
                'exchange': exchange,
                'asset_type': asset_type,
                'collection_date': datetime.now().isoformat(),
                'days_collected': len(combined_data),
                'features_structured': len(structured_data.columns) if not structured_data.empty else 0,
                'features_unstructured': ['news_headlines', 'news_count', 'news_sentiment_score'],
            },
            'data': combined_data,
            'structured_summary': self._get_data_summary(structured_data),
            'news_summary': f"{len(news_data)} articles collected",
        }
        return dataset

    def _collect_structured_data_safe(self, symbol: str, days: int) -> pd.DataFrame:
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days + 50)
            hist_data = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if hist_data.empty:
                return pd.DataFrame()
            if hasattr(hist_data.columns, 'nlevels') and hist_data.columns.nlevels > 1:
                hist_data.columns = hist_data.columns.get_level_values(0)
            hist_data = hist_data.reset_index()
            df = pd.DataFrame()
            df['Date'] = hist_data['Date']
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in hist_data.columns:
                    if col == 'Volume':
                        df[col] = hist_data[col].fillna(0).astype('int64')
                    else:
                        df[col] = hist_data[col].round(4)
                else:
                    df[col] = 0
            if 'Close' not in hist_data.columns or hist_data['Close'].isna().all():
                return pd.DataFrame()
            df = self._add_technical_features(df)
            df = df.dropna(subset=['Close']).tail(days).reset_index(drop=True)
            return df
        except Exception:
            return pd.DataFrame()

    def _add_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df['Daily_Return'] = df['Close'].pct_change().round(6)
            df['High_Low_Pct'] = ((df['High'] - df['Low']) / df['Close']).round(6)
            df['Close_Open_Pct'] = ((df['Close'] - df['Open']) / df['Open']).round(6)
            df['MA_5'] = df['Close'].rolling(window=5, min_periods=1).mean().round(4)
            df['MA_20'] = df['Close'].rolling(window=20, min_periods=10).mean().round(4)
            df['MA_Signal'] = ((df['MA_5'] - df['MA_20']) / df['MA_20']).round(6)
            df['Volatility_5'] = df['Daily_Return'].rolling(window=5, min_periods=1).std().round(6)
            df['Volatility_20'] = df['Daily_Return'].rolling(window=20, min_periods=5).std().round(6)
            df['Volume_MA_10'] = df['Volume'].rolling(window=10, min_periods=1).mean().round(0)
            df['Volume_Ratio'] = (df['Volume'] / (df['Volume_MA_10'] + 1)).round(4)
            df['Price_Change_5'] = ((df['Close'] - df['Close'].shift(5)) / (df['Close'].shift(5) + 0.001)).round(6)
            df['Price_Momentum'] = ((df['Close'] - df['Close'].shift(1)) / (df['Close'].shift(1) + 0.001)).round(6)
            df['High_5'] = df['High'].rolling(window=5, min_periods=1).max().round(4)
            df['Low_5'] = df['Low'].rolling(window=5, min_periods=1).min().round(4)
            df['Position_in_Range'] = ((df['Close'] - df['Low_5']) / (df['High_5'] - df['Low_5'] + 0.001)).round(4)
            df['Next_Day_Return'] = df['Daily_Return'].shift(-1).round(6)
            df = df.fillna(0)
            return df
        except Exception:
            return df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].fillna(0)

    def _scrape_news_data_multi_source(self, symbol: str, asset_type: str, days: int) -> List[Dict]:
        all_news: List[Dict] = []
        rss_news = self._scrape_rss_feeds(symbol, asset_type)
        if rss_news:
            all_news.extend(rss_news)
        web_news = self._scrape_google_news(symbol)
        if web_news:
            all_news.extend(web_news)
        processed_news = self._process_news_articles(all_news, symbol, days)
        return processed_news

    def _scrape_rss_feeds(self, symbol: str, asset_type: str) -> List[Dict]:
        feeds = [
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
            "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        ]
        if asset_type == 'crypto':
            feeds.extend([
                "https://feeds.feedburner.com/CoinDesk",
                "https://cointelegraph.com/rss",
            ])
        articles: List[Dict] = []
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:3]:
                    article = {
                        'title': entry.get('title', ''),
                        'summary': self._clean_html(entry.get('summary', '')),
                        'published_date': self._parse_rss_date(entry),
                        'source': 'rss_feed',
                        'url': entry.get('link', ''),
                        'relevance': 'medium',
                    }
                    if article['title']:
                        articles.append(article)
            except Exception:
                continue
        return articles

    def _scrape_google_news(self, symbol: str) -> List[Dict]:
        try:
            query = f"{symbol} stock market news"
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            articles = []
            for entry in feed.entries[:5]:
                article = {
                    'title': entry.get('title', ''),
                    'summary': self._clean_html(entry.get('summary', '')),
                    'published_date': self._parse_rss_date(entry),
                    'source': 'google_news',
                    'url': entry.get('link', ''),
                    'relevance': 'high',
                }
                if article['title']:
                    articles.append(article)
            return articles
        except Exception:
            return []

    def _parse_rss_date(self, entry) -> str:
        try:
            if 'published_parsed' in entry and entry.published_parsed:
                return datetime.fromtimestamp(time.mktime(entry.published_parsed)).isoformat()
        except Exception:
            pass
        return entry.get('published', datetime.now().isoformat())

    def _normalize_date(self, date_input) -> str:
        try:
            if isinstance(date_input, str):
                try:
                    parsed_date = datetime.fromisoformat(date_input.replace('Z', '+00:00'))
                except ValueError:
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                        try:
                            parsed_date = datetime.strptime(date_input.split('.')[0], fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        try:
                            parsed_date = email.utils.parsedate_to_datetime(date_input)
                        except Exception:
                            raise ValueError
            elif isinstance(date_input, datetime):
                parsed_date = date_input
            else:
                raise ValueError
            return parsed_date.strftime('%Y-%m-%d')
        except Exception:
            return datetime.now().strftime('%Y-%m-%d')

    def _process_news_articles(self, news_list: List[Dict], symbol: str, days: int) -> List[Dict]:
        processed_news: List[Dict] = []
        start_date = datetime.now() - timedelta(days=days)
        start_date_str = start_date.strftime('%Y-%m-%d')
        for article in news_list:
            if not article.get('title') or len(article['title']) < 5:
                continue
            text = (article['title'] + ' ' + article.get('summary', '')).lower()
            if symbol.lower() in text:
                article_date = self._normalize_date(article.get('published_date', ''))
                if article_date >= start_date_str:
                    article['sentiment_score'] = self._calculate_sentiment_score(article['title'], article.get('summary', ''))
                    processed_news.append(article)
        return processed_news[:30]

    def _calculate_sentiment_score(self, title: str, summary: str) -> float:
        text = (title + ' ' + summary).lower()
        positive_words = ['gains', 'rises', 'up', 'surge', 'rally', 'growth', 'profit', 'strong', 'positive']
        negative_words = ['falls', 'drops', 'down', 'decline', 'crash', 'loss', 'weak', 'negative']
        positive_count = sum(1 for w in positive_words if w in text)
        negative_count = sum(1 for w in negative_words if w in text)
        total_words = len(text.split())
        if total_words == 0:
            return 0.0
        sentiment = (positive_count - negative_count) / max(total_words / 20, 1)
        return max(-1.0, min(1.0, sentiment))

    def _align_data_by_date(self, structured_data: pd.DataFrame, news_data: List[Dict]) -> List[Dict]:
        if structured_data.empty:
            return []
        combined_records: List[Dict] = []
        for _, row in structured_data.iterrows():
            date = row['Date']
            date_str = self._normalize_date(date)
            relevant_news = []
            for article in news_data:
                article_date = self._normalize_date(article.get('published_date', ''))
                try:
                    article_date_obj = datetime.strptime(article_date, '%Y-%m-%d')
                    target_date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                except Exception:
                    continue
                delta_days = (article_date_obj - target_date_obj).days
                if abs(delta_days) <= 1 and article.get('title', ''):
                    relevant_news.append(article)
            relevant_news = sorted(relevant_news, key=lambda x: (x.get('relevance', 'low'), x.get('published_date', '')), reverse=True)
            news_headlines: List[str] = []
            sentiment_scores: List[float] = []
            for article in relevant_news[:3]:
                if article.get('title'):
                    news_headlines.append(article['title'])
                    sentiment_scores.append(article.get('sentiment_score', 0.0))
            record = row.to_dict()
            record['Date'] = date_str
            record['news_headlines'] = ' | '.join(news_headlines) if news_headlines else 'No major news'
            record['news_count'] = len(news_headlines)
            record['news_sentiment_score'] = float(np.mean(sentiment_scores)) if sentiment_scores else 0.0
            combined_records.append(record)
        return combined_records

    def _get_data_summary(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "No structured data"
        return f"{len(df)} days, {len(df.columns)} features"


