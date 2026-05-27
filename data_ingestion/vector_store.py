"""
Vector database implementation using ChromaDB.

Provides semantic search capabilities for stock documents,
enabling intelligent querying based on stock characteristics.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from .models import StockDocument, SearchResult, DataSource, PriceHistory, DividendRecord

# Import config for default paths and constants
try:
    from config import VECTORDB_DIR, MAX_PAYOUT_RATIO_PCT
    DEFAULT_VECTORDB_DIR = str(VECTORDB_DIR)
except ImportError:
    DEFAULT_VECTORDB_DIR = "data/vectordb"
    MAX_PAYOUT_RATIO_PCT = 150.0

logger = logging.getLogger(__name__)

# Try to import chromadb, provide fallback if not available
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. Install with: pip install chromadb")


class VectorStore:
    """
    Vector database for stock documents using ChromaDB.
    
    Features:
    - Semantic search by stock characteristics
    - Metadata filtering (sector, yield, streak, etc.)
    - Persistent storage
    - Document deduplication
    """
    
    COLLECTION_NAME = "dividend_stocks"
    
    def __init__(
        self,
        persist_directory: str = None,
        embedding_model: str = "default",
    ):
        """
        Initialize vector store.
        
        Args:
            persist_directory: Directory for persistent storage. Defaults to ~/.dividendscope/data/vectordb.
            embedding_model: Embedding model to use (default uses ChromaDB's built-in).
        """
        from db.connection import use_cloud_sql

        self._use_postgres = use_cloud_sql()
        self._pg_store = None
        if self._use_postgres:
            from db.postgres_market_store import PostgresMarketStore

            self._pg_store = PostgresMarketStore()
            self.persist_directory = Path(persist_directory or DEFAULT_VECTORDB_DIR)
            self._use_fallback = False
            logger.info("Market library using PostgreSQL (stock_documents)")
            return

        if persist_directory is None:
            persist_directory = DEFAULT_VECTORDB_DIR
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        self._client = None
        self._collection = None
        self._fallback_store: Dict[str, StockDocument] = {}
        self._fallback_file = self.persist_directory / "fallback_store.json"
        self._use_fallback = not CHROMADB_AVAILABLE
        
        if CHROMADB_AVAILABLE:
            self._init_chromadb()
        else:
            self._init_fallback()
    
    def _init_chromadb(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False),
            )
            
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={
                    "description": "Dividend stock documents for analysis",
                    "created": datetime.now().isoformat(),
                },
            )
            
            logger.info(f"ChromaDB initialized at {self.persist_directory}")
            logger.info(f"Collection '{self.COLLECTION_NAME}' has {self._collection.count()} documents")
            
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {e}")
            self._use_fallback = True
            self._init_fallback()
    
    def _init_fallback(self) -> None:
        """Initialize fallback JSON-based storage."""
        if self._fallback_file.exists():
            try:
                with open(self._fallback_file, "r") as f:
                    data = json.load(f)
                    self._fallback_store = {
                        k: StockDocument.from_dict(v) 
                        for k, v in data.items()
                    }
                logger.info(f"Loaded {len(self._fallback_store)} documents from fallback store")
            except Exception as e:
                logger.error(f"Error loading fallback store: {e}")
                self._fallback_store = {}
        
        logger.info("Using fallback JSON storage (install chromadb for vector search)")
    
    def _save_fallback(self) -> None:
        """Save fallback store to disk."""
        try:
            data = {k: v.to_full_dict() for k, v in self._fallback_store.items()}
            with open(self._fallback_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving fallback store: {e}")
    
    def add_document(self, document: StockDocument) -> str:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.add_document(document)
        """
        Add a document to the vector store.
        
        Args:
            document: StockDocument to add.
            
        Returns:
            Document ID.
        """
        doc_id = document.document_id
        
        if self._use_fallback:
            self._fallback_store[doc_id] = document
            self._save_fallback()
            return doc_id
        
        try:
            # Check if document exists
            existing = self._collection.get(ids=[doc_id])
            
            if existing and existing["ids"]:
                # Update existing document
                self._collection.update(
                    ids=[doc_id],
                    documents=[document.embedding_text],
                    metadatas=[document.to_metadata()],
                )
            else:
                # Add new document
                self._collection.add(
                    ids=[doc_id],
                    documents=[document.embedding_text],
                    metadatas=[document.to_metadata()],
                )
            
            return doc_id
            
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {e}")
            # Fallback to JSON
            self._fallback_store[doc_id] = document
            self._save_fallback()
            return doc_id
    
    def add_documents(self, documents: List[StockDocument]) -> List[str]:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.add_documents(documents)
        """
        Add multiple documents to the vector store.
        
        Args:
            documents: List of StockDocuments to add.
            
        Returns:
            List of document IDs.
        """
        if not documents:
            return []

        ids = []
        
        if self._use_fallback:
            for doc in documents:
                doc_id = doc.document_id
                self._fallback_store[doc_id] = doc
                ids.append(doc_id)
            self._save_fallback()
            return ids
        
        # Batch add for ChromaDB
        try:
            doc_ids = [d.document_id for d in documents]
            doc_texts = [d.embedding_text for d in documents]
            doc_metadatas = [d.to_metadata() for d in documents]
            
            # Split into add vs update
            existing = self._collection.get(ids=doc_ids)
            existing_ids = set(existing["ids"]) if existing else set()
            
            new_docs = [
                (i, t, m) for i, t, m in zip(doc_ids, doc_texts, doc_metadatas)
                if i not in existing_ids
            ]
            
            update_docs = [
                (i, t, m) for i, t, m in zip(doc_ids, doc_texts, doc_metadatas)
                if i in existing_ids
            ]
            
            if new_docs:
                self._collection.add(
                    ids=[d[0] for d in new_docs],
                    documents=[d[1] for d in new_docs],
                    metadatas=[d[2] for d in new_docs],
                )
            
            if update_docs:
                self._collection.update(
                    ids=[d[0] for d in update_docs],
                    documents=[d[1] for d in update_docs],
                    metadatas=[d[2] for d in update_docs],
                )
            
            return doc_ids
            
        except Exception as e:
            logger.error(f"Error batch adding documents: {e}")
            # Fallback
            for doc in documents:
                self._fallback_store[doc.document_id] = doc
                ids.append(doc.document_id)
            self._save_fallback()
            return ids
    
    def search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.search(query, n_results, where)
        """
        Search for documents by semantic similarity.
        
        Args:
            query: Search query text.
            n_results: Maximum number of results.
            where: Metadata filter (ChromaDB where clause).
            
        Returns:
            List of SearchResults sorted by relevance.
        """
        if self._use_fallback:
            return self._fallback_search(query, n_results, where)
        
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
            )
            
            search_results = []
            
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0
                    
                    # Convert distance to similarity score (0-1)
                    score = 1 / (1 + distance)
                    
                    # Reconstruct document from metadata
                    doc = self._metadata_to_document(metadata)
                    
                    search_results.append(SearchResult(document=doc, score=score))
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return self._fallback_search(query, n_results, where)
    
    def _fallback_search(
        self,
        query: str,
        n_results: int,
        where: Optional[Dict[str, Any]],
    ) -> List[SearchResult]:
        """Simple keyword-based fallback search."""
        query_lower = query.lower()
        query_terms = query_lower.split()
        
        results = []
        
        for doc in self._fallback_store.values():
            # Apply where filter
            if where and not self._matches_filter(doc, where):
                continue
            
            # Calculate simple relevance score
            text = doc.embedding_text.lower()
            score = sum(1 for term in query_terms if term in text)
            
            if score > 0:
                results.append(SearchResult(document=doc, score=score / len(query_terms)))
        
        # Sort by score and limit
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:n_results]
    
    def _matches_filter(self, doc: StockDocument, where: Dict[str, Any]) -> bool:
        """Check if document matches filter criteria."""
        metadata = doc.to_metadata()
        
        for key, value in where.items():
            if key.startswith("$"):
                # Handle operators like $gt, $lt, etc.
                continue
            
            if key not in metadata:
                return False
            
            if isinstance(value, dict):
                # Handle comparison operators
                for op, val in value.items():
                    if op == "$gt" and not (metadata[key] and metadata[key] > val):
                        return False
                    elif op == "$gte" and not (metadata[key] and metadata[key] >= val):
                        return False
                    elif op == "$lt" and not (metadata[key] and metadata[key] < val):
                        return False
                    elif op == "$lte" and not (metadata[key] and metadata[key] <= val):
                        return False
                    elif op == "$eq" and metadata[key] != val:
                        return False
            else:
                if metadata[key] != value:
                    return False
        
        return True
    
    def _metadata_to_document(self, metadata: Dict[str, Any]) -> StockDocument:
        """Reconstruct StockDocument from metadata."""
        import json
        from datetime import date
        
        # Deserialize price history from JSON
        price_history = []
        if metadata.get("price_history_json"):
            try:
                price_data = json.loads(metadata["price_history_json"])
                price_history = [PriceHistory.from_dict(p) for p in price_data]
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Error deserializing price history: {e}")
        
        # Deserialize dividend history from JSON
        dividend_history = []
        if metadata.get("dividend_history_json"):
            try:
                div_data = json.loads(metadata["dividend_history_json"])
                dividend_history = [DividendRecord.from_dict(d) for d in div_data]
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Error deserializing dividend history: {e}")
        
        # Parse ex-dividend date
        ex_div_date = None
        if metadata.get("ex_dividend_date"):
            try:
                ex_div_date = date.fromisoformat(metadata["ex_dividend_date"])
            except (ValueError, TypeError):
                pass
        
        return StockDocument(
            symbol=metadata.get("symbol", ""),
            name=metadata.get("name", ""),
            sector=metadata.get("sector", "Unknown"),
            industry=metadata.get("industry", "Unknown"),
            exchange=metadata.get("exchange", "Unknown"),
            # Dividend fields
            dividend_yield=metadata.get("dividend_yield"),
            annual_dividend=metadata.get("annual_dividend"),
            dividend_streak_years=metadata.get("dividend_streak_years"),
            payout_ratio=metadata.get("payout_ratio"),
            fcf_payout_ratio=metadata.get("fcf_payout_ratio"),
            dividend_coverage=metadata.get("dividend_coverage"),
            ex_dividend_date=ex_div_date,
            payment_frequency=metadata.get("payment_frequency", 4),
            dividend_cagr_5y=metadata.get("dividend_cagr_5y"),
            dividend_cagr_10y=metadata.get("dividend_cagr_10y"),
            dividend_total_years=metadata.get("dividend_total_years"),
            # Price data
            current_price=metadata.get("current_price"),
            market_cap=metadata.get("market_cap"),
            fifty_two_week_high=metadata.get("fifty_two_week_high"),
            fifty_two_week_low=metadata.get("fifty_two_week_low"),
            beta=metadata.get("beta"),
            # Valuation
            pe_ratio=metadata.get("pe_ratio"),
            forward_pe=metadata.get("forward_pe"),
            peg_ratio=metadata.get("peg_ratio"),
            price_to_book=metadata.get("price_to_book"),
            price_to_sales=metadata.get("price_to_sales"),
            ev_ebitda=metadata.get("ev_ebitda"),
            # Financial health
            debt_to_equity=metadata.get("debt_to_equity"),
            debt_to_ebitda=metadata.get("debt_to_ebitda"),
            interest_coverage=metadata.get("interest_coverage"),
            current_ratio=metadata.get("current_ratio"),
            quick_ratio=metadata.get("quick_ratio"),
            # Profitability
            roe=metadata.get("roe"),
            roa=metadata.get("roa"),
            roic=metadata.get("roic"),
            profit_margin=metadata.get("profit_margin"),
            operating_margin=metadata.get("operating_margin"),
            gross_margin=metadata.get("gross_margin"),
            # Growth
            revenue_growth=metadata.get("revenue_growth"),
            earnings_growth=metadata.get("earnings_growth"),
            fcf_growth=metadata.get("fcf_growth"),
            # Performance
            price_return_1y=metadata.get("price_return_1y"),
            total_return_1y=metadata.get("total_return_1y"),
            price_return_5y=metadata.get("price_return_5y"),
            total_return_5y=metadata.get("total_return_5y"),
            # Analyst
            target_price=metadata.get("target_price"),
            target_upside=metadata.get("target_upside"),
            analyst_rating=metadata.get("analyst_rating"),
            num_analysts=metadata.get("num_analysts"),
            # Historical
            price_history=price_history,
            dividend_history=dividend_history,
            # Metadata
            source=DataSource(metadata.get("source", "manual")),
            data_quality=metadata.get("data_quality", 0),
            description=metadata.get("description", ""),
            notes=metadata.get("notes", ""),
            in_portfolio=bool(metadata.get("in_portfolio", False)),
            portfolio_shares=metadata.get("portfolio_shares"),
            portfolio_avg_cost_per_share=metadata.get("portfolio_avg_cost_per_share"),
            portfolio_acquisition_value=metadata.get("portfolio_acquisition_value"),
            portfolio_dividends_paid=metadata.get("portfolio_dividends_paid"),
            portfolio_purchase_count=metadata.get("portfolio_purchase_count"),
        )
    
    def get_by_symbol(self, symbol: str) -> Optional[StockDocument]:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.get_by_symbol(symbol)
        """
        Get document by stock symbol.
        
        Returns the highest quality document if multiple exist for the same symbol.
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            StockDocument or None.
        """
        if self._use_fallback:
            matches = [
                doc for doc in self._fallback_store.values()
                if doc.symbol.upper() == symbol.upper()
            ]
            if not matches:
                return None
            # Return highest quality
            return max(matches, key=lambda d: d.data_quality or 0)
        
        try:
            # Get ALL documents for this symbol
            results = self._collection.get(
                where={"symbol": symbol.upper()},
            )
            
            if results and results["ids"]:
                # Reconstruct all documents
                documents = [
                    self._metadata_to_document(meta)
                    for meta in results["metadatas"]
                ]
                
                # Prefer documents with enriched data (valuation, profitability, etc.)
                def completeness_score(doc: StockDocument) -> float:
                    score = doc.data_quality or 0
                    
                    # Bonus for enriched fields that only come from yfinance
                    if doc.forward_pe is not None:
                        score += 5
                    if doc.roe is not None:
                        score += 5
                    if doc.profit_margin is not None:
                        score += 5
                    if doc.target_price is not None:
                        score += 5
                    if doc.debt_to_equity is not None:
                        score += 5
                    if doc.beta is not None:
                        score += 3
                    if doc.dividend_cagr_5y is not None:
                        score += 5
                    if doc.analyst_rating is not None:
                        score += 3
                    
                    # Prefer yahoo source for real-time enriched data
                    if doc.source.value == "yahoo":
                        score += 10
                    
                    return score
                
                return max(documents, key=completeness_score)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting {symbol}: {e}")
            return None
    
    def get_dividend_kings(self, min_streak: int = 50) -> List[StockDocument]:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.get_dividend_kings(min_streak)
        """
        Get all Dividend Kings (50+ years of increases).
        
        Args:
            min_streak: Minimum consecutive years.
            
        Returns:
            List of StockDocuments.
        """
        if self._use_fallback:
            return [
                doc for doc in self._fallback_store.values()
                if doc.dividend_streak_years and doc.dividend_streak_years >= min_streak
            ]
        
        try:
            results = self._collection.get(
                where={"dividend_streak_years": {"$gte": min_streak}},
            )
            
            documents = []
            if results and results["ids"]:
                for metadata in results["metadatas"]:
                    documents.append(self._metadata_to_document(metadata))
            
            return documents
            
        except Exception as e:
            logger.error(f"Error getting dividend kings: {e}")
            return []
    
    def get_by_sector(self, sector: str) -> List[StockDocument]:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.get_by_sector(sector)
        """Get all documents in a sector."""
        if self._use_fallback:
            return [
                doc for doc in self._fallback_store.values()
                if doc.sector.lower() == sector.lower()
            ]
        
        try:
            results = self._collection.get(
                where={"sector": sector},
            )
            
            documents = []
            if results and results["ids"]:
                for metadata in results["metadatas"]:
                    documents.append(self._metadata_to_document(metadata))
            
            return documents
            
        except Exception as e:
            logger.error(f"Error getting sector {sector}: {e}")
            return []
    
    def count(self) -> int:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.count()
        """Get total number of documents."""
        if self._use_fallback:
            return len(self._fallback_store)
        
        try:
            return self._collection.count()
        except Exception:
            return len(self._fallback_store)
    
    def get_stats(self) -> Dict[str, Any]:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.get_stats()
        """
        Get comprehensive statistics about the vector store.
        
        Returns:
            Dict with statistics including document counts, sectors, etc.
        """
        stats: Dict[str, Any] = {
            "total_documents": 0,
            "dividend_kings": 0,
            "dividend_aristocrats": 0,
            "unique_symbols": 0,
            "sectors": {},
            "sources": {},
        }
        
        try:
            # Get all documents
            if self._use_fallback:
                documents = list(self._fallback_store.values())
            else:
                results = self._collection.get()
                documents = []
                if results and results["metadatas"]:
                    for metadata in results["metadatas"]:
                        documents.append(self._metadata_to_document(metadata))
            
            stats["total_documents"] = len(documents)
            
            symbols = set()
            sectors: Dict[str, int] = {}
            sources: Dict[str, int] = {}
            kings = 0
            aristocrats = 0
            
            for doc in documents:
                symbols.add(doc.symbol)
                
                # Count by sector
                sector = doc.sector or "Unknown"
                sectors[sector] = sectors.get(sector, 0) + 1
                
                # Count by source
                source = doc.source.value if doc.source else "unknown"
                sources[source] = sources.get(source, 0) + 1
                
                # Count dividend tiers
                if doc.dividend_streak_years:
                    if doc.dividend_streak_years >= 50:
                        kings += 1
                    elif doc.dividend_streak_years >= 25:
                        aristocrats += 1
            
            stats["unique_symbols"] = len(symbols)
            stats["dividend_kings"] = kings
            stats["dividend_aristocrats"] = aristocrats
            stats["sectors"] = dict(sorted(sectors.items(), key=lambda x: x[1], reverse=True))
            stats["sources"] = dict(sorted(sources.items(), key=lambda x: x[1], reverse=True))
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
        
        return stats
    
    def clear(self) -> None:
        if getattr(self, "_use_postgres", False):
            self._pg_store.clear()
            return
        """Clear all documents from the store."""
        if self._use_fallback:
            self._fallback_store = {}
            self._save_fallback()
            return
        
        try:
            self._client.delete_collection(self.COLLECTION_NAME)
            self._collection = self._client.create_collection(
                name=self.COLLECTION_NAME,
                metadata={"description": "Dividend stock documents for analysis"},
            )
            logger.info("Vector store cleared")
        except Exception as e:
            logger.error(f"Error clearing store: {e}")

    def delete_symbols(self, symbols: List[str]) -> int:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.delete_symbols(symbols)
        """
        Remove all documents for the given ticker symbols.

        Returns:
            Number of documents removed.
        """
        if not symbols:
            return 0

        removed = 0
        targets = {symbol.upper() for symbol in symbols}

        if self._use_fallback:
            to_delete = [
                doc_id
                for doc_id, doc in self._fallback_store.items()
                if doc.symbol.upper() in targets
            ]
            for doc_id in to_delete:
                del self._fallback_store[doc_id]
                removed += 1
            if to_delete:
                self._save_fallback()
            return removed

        try:
            for symbol in targets:
                results = self._collection.get(where={"symbol": symbol})
                if results and results.get("ids"):
                    self._collection.delete(ids=results["ids"])
                    removed += len(results["ids"])
                    logger.info("Removed %s document(s) for %s", len(results["ids"]), symbol)
        except Exception as e:
            logger.error("Error deleting symbols %s: %s", targets, e)

        return removed
    
    def export_to_json(self, filepath: str) -> int:
        """
        Export all documents to JSON file.
        
        Args:
            filepath: Output file path.
            
        Returns:
            Number of documents exported.
        """
        documents = []
        
        if self._use_fallback:
            documents = list(self._fallback_store.values())
        else:
            try:
                results = self._collection.get()
                if results and results["ids"]:
                    for metadata in results["metadatas"]:
                        documents.append(self._metadata_to_document(metadata))
            except Exception as e:
                logger.error(f"Error exporting: {e}")
        
        with open(filepath, "w") as f:
            json.dump([d.to_full_dict() for d in documents], f, indent=2)
        
        return len(documents)
    
    def import_from_json(self, filepath: str) -> int:
        """
        Import documents from JSON file.
        
        Args:
            filepath: Input file path.
            
        Returns:
            Number of documents imported.
        """
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            documents = [StockDocument.from_dict(d) for d in data]
            self.add_documents(documents)
            
            return len(documents)
        except Exception as e:
            logger.error(f"Error importing: {e}")
            return 0
    
    def get_all_documents(self) -> List[StockDocument]:
        if getattr(self, "_use_postgres", False):
            return self._pg_store.get_all_documents()
        """
        Get all documents from the store.
        
        Returns:
            List of all StockDocuments.
        """
        if self._use_fallback:
            return list(self._fallback_store.values())
        
        try:
            results = self._collection.get()
            if results and results["metadatas"]:
                return [self._metadata_to_document(meta) for meta in results["metadatas"]]
        except Exception as e:
            logger.error(f"Error getting all documents: {e}")
        
        return []
    
    def consolidate_duplicates(self) -> Dict[str, Any]:
        """
        Consolidate duplicate documents by symbol, keeping the best version.
        
        This removes duplicates by:
        1. Grouping all documents by symbol
        2. Merging data from all versions (preferring enriched data)
        3. Replacing all duplicates with a single consolidated document
        
        Returns:
            Stats about the consolidation.
        """
        stats = {
            "total_before": 0,
            "unique_symbols": 0,
            "duplicates_removed": 0,
            "total_after": 0,
        }
        
        all_docs = self.get_all_documents()
        stats["total_before"] = len(all_docs)
        
        if not all_docs:
            return stats
        
        # Group by symbol
        by_symbol: Dict[str, List[StockDocument]] = {}
        for doc in all_docs:
            symbol = doc.symbol.upper()
            if symbol not in by_symbol:
                by_symbol[symbol] = []
            by_symbol[symbol].append(doc)
        
        stats["unique_symbols"] = len(by_symbol)
        
        # Merge duplicates - keep best data from each version
        consolidated: List[StockDocument] = []
        
        for symbol, docs in by_symbol.items():
            if len(docs) == 1:
                # No duplicates - trim history and keep
                docs[0].trim_history()
                consolidated.append(docs[0])
            else:
                # Multiple versions - merge them
                best = self._merge_documents(docs)
                best.trim_history()
                consolidated.append(best)
        
        stats["duplicates_removed"] = stats["total_before"] - len(consolidated)
        
        # Clear and rebuild with consolidated documents
        self.clear()
        self.add_documents(consolidated)
        
        stats["total_after"] = len(consolidated)
        
        return stats
    
    def fix_invalid_values(self) -> Dict[str, Any]:
        """
        Fix invalid/corrupt values in the database.
        
        Fixes:
        - Dividend yields > 30% (likely multiplied by 100 twice)
        - Payout ratios > 150% (capped; likely corrupt)
        - Missing dividend streak for known Dividend Kings
        
        Returns:
            Stats about the fixes applied.
        """
        stats = {
            "total_documents": 0,
            "yield_fixes": 0,
            "payout_fixes": 0,
            "streak_fixes": 0,
        }
        
        all_docs = self.get_all_documents()
        stats["total_documents"] = len(all_docs)
        
        modified = []
        
        for doc in all_docs:
            changed = False
            
            # Fix dividend yield > 30% (divide by 100)
            if doc.dividend_yield is not None and doc.dividend_yield > 30:
                doc.dividend_yield = doc.dividend_yield / 100
                stats["yield_fixes"] += 1
                changed = True
                logger.info(f"{doc.symbol}: Fixed dividend yield to {doc.dividend_yield:.2f}%")
            
            # Fix payout ratio that's way too high (> 1000% stored as multiplied 10000x)
            # e.g., 13333 should be 133.33%
            if doc.payout_ratio is not None and doc.payout_ratio > 1000:
                doc.payout_ratio = doc.payout_ratio / 100
                stats["payout_fixes"] += 1
                changed = True
                logger.info(f"{doc.symbol}: Fixed payout ratio (10000x) to {doc.payout_ratio:.2f}%")
            
            # Fix likely double-multiplied payout: 300–500% often means 3–5% (stored as 5 then *100)
            # e.g. 500 might mean 5%, 350 might mean 3.5%
            if doc.payout_ratio is not None and 300 < doc.payout_ratio <= 500:
                candidate = doc.payout_ratio / 100
                if 0 < candidate <= 150:
                    doc.payout_ratio = candidate
                    stats["payout_fixes"] += 1
                    changed = True
                    logger.info(f"{doc.symbol}: Fixed payout ratio (double-multiplied) to {doc.payout_ratio:.2f}%")
            
            # Only treat decimal ratio (0, 1) as needing *100. Values in [1, 10] are already % (e.g. 5 = 5%)
            # so we must NOT multiply them or we get 500% from 5%.
            if doc.payout_ratio is not None and 0 < doc.payout_ratio < 1:
                doc.payout_ratio = doc.payout_ratio * 100
                stats["payout_fixes"] += 1
                changed = True
                logger.info(f"{doc.symbol}: Fixed payout ratio (decimal) to {doc.payout_ratio:.2f}%")
            
            # Cap extreme payout (REITs/special cases can be 100–150%; higher is usually bad data)
            if doc.payout_ratio is not None and doc.payout_ratio > MAX_PAYOUT_RATIO_PCT:
                logger.warning(f"{doc.symbol}: Capping payout ratio {doc.payout_ratio:.1f}% to {MAX_PAYOUT_RATIO_PCT:.0f}%")
                doc.payout_ratio = float(MAX_PAYOUT_RATIO_PCT)
                stats["payout_fixes"] += 1
                changed = True

            from utils.dividend_streak import apply_dividend_streak_to_document

            previous_streak = doc.dividend_streak_years
            apply_dividend_streak_to_document(doc)
            if doc.dividend_streak_years != previous_streak:
                stats["streak_fixes"] += 1
                changed = True
                logger.info(
                    f"{doc.symbol}: Updated dividend streak to {doc.dividend_streak_years}"
                )
            
            if changed:
                doc.last_updated = datetime.now()
                modified.append(doc)
        
        # Update modified documents
        if modified:
            for doc in modified:
                self.add_document(doc)
        
        return stats
    
    def _merge_documents(self, docs: List[StockDocument]) -> StockDocument:
        """
        Merge multiple documents for the same symbol into one.
        
        Prioritizes:
        1. Yahoo/enriched data over basic data
        2. More recent last_updated timestamps
        3. Higher data quality scores
        4. Non-null values over null values
        """
        if not docs:
            raise ValueError("Cannot merge empty document list")
        
        if len(docs) == 1:
            return docs[0]
        
        # Sort by preference: yahoo source first, then by quality, then by recency
        def sort_key(d: StockDocument) -> tuple:
            is_yahoo = 1 if d.source == DataSource.YAHOO else 0
            quality = d.data_quality or 0
            updated = d.last_updated.timestamp() if d.last_updated else 0
            return (is_yahoo, quality, updated)
        
        docs.sort(key=sort_key, reverse=True)
        
        # Start with the best document
        best = docs[0]
        
        # Merge fields from other documents (fill in missing values)
        for doc in docs[1:]:
            # Core fields - prefer non-empty values
            if not best.name and doc.name:
                best.name = doc.name
            if best.sector in ("Unknown", "") and doc.sector not in ("Unknown", ""):
                best.sector = doc.sector
            if best.industry in ("Unknown", "") and doc.industry not in ("Unknown", ""):
                best.industry = doc.industry
            
            # Dividend fields
            if best.dividend_yield is None and doc.dividend_yield is not None:
                best.dividend_yield = doc.dividend_yield
            if best.annual_dividend is None and doc.annual_dividend is not None:
                best.annual_dividend = doc.annual_dividend
            if best.dividend_streak_years is None and doc.dividend_streak_years is not None:
                best.dividend_streak_years = doc.dividend_streak_years
            if best.payout_ratio is None and doc.payout_ratio is not None:
                best.payout_ratio = doc.payout_ratio
            
            # Valuation metrics
            if best.pe_ratio is None and doc.pe_ratio is not None:
                best.pe_ratio = doc.pe_ratio
            if best.forward_pe is None and doc.forward_pe is not None:
                best.forward_pe = doc.forward_pe
            if best.price_to_book is None and doc.price_to_book is not None:
                best.price_to_book = doc.price_to_book
            
            # Profitability
            if best.roe is None and doc.roe is not None:
                best.roe = doc.roe
            if best.profit_margin is None and doc.profit_margin is not None:
                best.profit_margin = doc.profit_margin
            
            # Financial health
            if best.debt_to_equity is None and doc.debt_to_equity is not None:
                best.debt_to_equity = doc.debt_to_equity
            if best.current_ratio is None and doc.current_ratio is not None:
                best.current_ratio = doc.current_ratio
            
            # Analyst data
            if best.target_price is None and doc.target_price is not None:
                best.target_price = doc.target_price
            if best.analyst_rating is None and doc.analyst_rating is not None:
                best.analyst_rating = doc.analyst_rating
            
            # Merge historical data (combine and deduplicate)
            if doc.price_history:
                existing_dates = {p.date for p in best.price_history} if best.price_history else set()
                for price in doc.price_history:
                    if price.date not in existing_dates:
                        if best.price_history is None:
                            best.price_history = []
                        best.price_history.append(price)
                        existing_dates.add(price.date)
            
            if doc.dividend_history:
                existing_dates = {d.ex_date for d in best.dividend_history} if best.dividend_history else set()
                for div in doc.dividend_history:
                    if div.ex_date not in existing_dates:
                        if best.dividend_history is None:
                            best.dividend_history = []
                        best.dividend_history.append(div)
                        existing_dates.add(div.ex_date)
        
        # Update timestamp
        best.last_updated = datetime.now()

        from utils.dividend_streak import apply_dividend_streak_to_document

        apply_dividend_streak_to_document(best)
        
        return best
