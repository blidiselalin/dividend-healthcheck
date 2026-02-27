"""Services for Dividend Kings Analysis."""

from .scoring import Recommendation, ScoringService
from .sector_service import SectorService
from .stock_service import StockService

__all__ = [
    "Recommendation",
    "ScoringService",
    "SectorService",
    "StockService",
]

# Optional enhanced service (requires data_ingestion module)
try:
    from .enhanced_stock_service import EnhancedStockService
    __all__.append("EnhancedStockService")
except ImportError:
    pass

# Optional PDF report generator (requires reportlab)
try:
    from .report_generator import ReportGenerator, generate_stock_report
    __all__.extend(["ReportGenerator", "generate_stock_report"])
except ImportError:
    pass

# Optional yield channel chart service (requires plotly)
try:
    from .yield_channel_chart import YieldChannelService, YieldChannelData, is_available
    __all__.extend(["YieldChannelService", "YieldChannelData"])
except ImportError:
    pass

# Optional news service (requires yfinance, feedparser optional)
try:
    from .news_service import NewsService, NewsSummary, NewsArticle
    __all__.extend(["NewsService", "NewsSummary", "NewsArticle"])
except ImportError:
    pass

# VectorDB-first service (requires data_ingestion module)
try:
    from .vectordb_service import VectorDBService, get_vectordb_service
    __all__.extend(["VectorDBService", "get_vectordb_service"])
except ImportError:
    pass
