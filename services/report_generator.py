"""
PDF Report Generator for Dividend Kings Analyzer.

Generates comprehensive research reports similar to professional
financial research documents with:
- Rate Card (score, yields, growth rates)
- Financial Data (income statement, balance sheet, cash flow)
- Financial Ratios
- Dividend History
- Valuation Analysis
"""

import io
import logging
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from utils.formatting import (
    format_currency,
    format_percent,
    format_number,
    format_large_number,
    format_delta,
    format_delta_pct,
)

logger = logging.getLogger(__name__)

# Check if reportlab is available
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        PageBreak, Image, HRFlowable
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Only import StockData for type checking to avoid circular imports
if TYPE_CHECKING:
    from models.stock import StockData


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    page_size: Tuple[float, float] = dataclass_field(
        default_factory=lambda: (595.27, 841.89)  # A4 in points
    )
    margin: float = 36.0  # 0.5 inch in points
    title_font_size: int = 16
    header_font_size: int = 12
    body_font_size: int = 9
    table_font_size: int = 8
    include_financials: bool = True
    include_dividend_history: bool = True
    include_charts: bool = False
    years_of_history: int = 10


# Only define ReportGenerator if reportlab is available
if REPORTLAB_AVAILABLE:
    from models.stock import StockData
    
    class ReportGenerator:
        """
        Generates PDF research reports for dividend stocks.
        
        Report sections:
        1. Rate Card - Key metrics and scores
        2. Dividend Analysis - Yields, growth rates, channels
        3. Valuation - P/E, DCF, Gordon Growth Model
        4. Financial Data - Income statement, balance sheet, cash flow
        5. Financial Ratios - ROE, margins, payout ratios
        6. Dividend History - Historical payments
        """
        
        # Color scheme
        COLORS = {
            "header_bg": colors.HexColor("#1a237e"),
            "header_text": colors.white,
            "section_bg": colors.HexColor("#e8eaf6"),
            "positive": colors.HexColor("#2e7d32"),
            "negative": colors.HexColor("#c62828"),
            "neutral": colors.HexColor("#424242"),
            "highlight": colors.HexColor("#fff176"),
        }
        
        def __init__(self, config: Optional[ReportConfig] = None):
            """Initialize report generator."""
            self.config = config or ReportConfig()
            self.config.page_size = A4
            self.config.margin = 0.5 * inch
            self.styles = getSampleStyleSheet()
            self._setup_styles()
        
        def _setup_styles(self) -> None:
            """Configure custom paragraph styles."""
            self.styles.add(ParagraphStyle(
                name="ReportTitle",
                parent=self.styles["Heading1"],
                fontSize=self.config.title_font_size,
                textColor=self.COLORS["header_bg"],
                spaceAfter=12,
            ))
            
            self.styles.add(ParagraphStyle(
                name="SectionHeader",
                parent=self.styles["Heading2"],
                fontSize=self.config.header_font_size,
                textColor=self.COLORS["header_bg"],
                spaceBefore=12,
                spaceAfter=6,
            ))
            
            self.styles.add(ParagraphStyle(
                name="TableHeader",
                parent=self.styles["Normal"],
                fontSize=self.config.table_font_size,
                textColor=self.COLORS["header_text"],
                alignment=TA_CENTER,
            ))
            
            self.styles.add(ParagraphStyle(
                name="TableCell",
                parent=self.styles["Normal"],
                fontSize=self.config.table_font_size,
                alignment=TA_RIGHT,
            ))
            
            self.styles.add(ParagraphStyle(
                name="ScorePositive",
                parent=self.styles["Normal"],
                fontSize=self.config.body_font_size,
                textColor=self.COLORS["positive"],
            ))
            
            self.styles.add(ParagraphStyle(
                name="ScoreNegative",
                parent=self.styles["Normal"],
                fontSize=self.config.body_font_size,
                textColor=self.COLORS["negative"],
            ))
        
        def generate(
            self,
            stock: "StockData",
            score: int,
            recommendation: str,
            pros: List[str],
            cons: List[str],
            historical_data: Optional[Dict[str, Any]] = None,
        ) -> bytes:
            """
            Generate a PDF report for a stock.
            
            Args:
                stock: StockData with current metrics.
                score: Investment score (0-100).
                recommendation: Recommendation label.
                pros: List of strengths.
                cons: List of concerns.
                historical_data: Optional dict with financial history.
                
            Returns:
                PDF file as bytes.
            """
            buffer = io.BytesIO()
            
            doc = SimpleDocTemplate(
                buffer,
                pagesize=self.config.page_size,
                leftMargin=self.config.margin,
                rightMargin=self.config.margin,
                topMargin=self.config.margin,
                bottomMargin=self.config.margin,
            )
            
            elements = []
            
            # Title
            elements.extend(self._build_title(stock))
            
            # Rate Card
            elements.extend(self._build_rate_card(stock, score, recommendation))
            
            # Dividend Analysis
            elements.extend(self._build_dividend_analysis(stock))
            
            # Valuation
            elements.extend(self._build_valuation(stock))
            
            # Investment Thesis
            elements.extend(self._build_thesis(pros, cons))
            
            # Financial Data (if available)
            if historical_data and self.config.include_financials:
                elements.append(PageBreak())
                elements.extend(self._build_financials(stock, historical_data))
            
            # Footer
            elements.extend(self._build_footer(stock))
            
            doc.build(elements)
            
            buffer.seek(0)
            return buffer.read()
        
        def _build_title(self, stock: "StockData") -> List:
            """Build report title section."""
            elements = []
            
            title = f"{stock.name} ({stock.symbol})"
            elements.append(Paragraph(title, self.styles["ReportTitle"]))
            
            tier = stock.dividend_tier if hasattr(stock, "dividend_tier") else "Stock"
            subtitle = f"Dividend {tier} | {stock.sector} | Research Report"
            elements.append(Paragraph(subtitle, self.styles["Normal"]))
            
            date_str = f"Report generated: {datetime.now().strftime('%B %d, %Y')}"
            elements.append(Paragraph(date_str, self.styles["Normal"]))
            
            elements.append(Spacer(1, 12))
            elements.append(HRFlowable(width="100%", thickness=1, color=self.COLORS["header_bg"]))
            elements.append(Spacer(1, 12))
            
            return elements
        
        def _build_rate_card(
            self,
            stock: "StockData",
            score: int,
            recommendation: str,
        ) -> List:
            """Build the rate card section with key metrics."""
            elements = []
            
            elements.append(Paragraph("RATE CARD", self.styles["SectionHeader"]))
            
            data = [
                ["Metric", "Value", "Metric", "Value"],
                [
                    "Score",
                    f"{score}/100",
                    "Recommendation",
                    recommendation,
                ],
                [
                    "Current Price",
                    self._fmt_currency(stock.price),
                    "Market Cap",
                    self._fmt_market_cap(stock.market_cap),
                ],
                [
                    "Dividend Yield",
                    self._fmt_percent(stock.dividend_yield_pct),
                    "Annual Dividend",
                    self._fmt_currency(stock.dividend_rate),
                ],
                [
                    "Div Streak (Years)",
                    str(stock.dividend_history.consecutive_years) if stock.dividend_history else "N/A",
                    "Dividend Tier",
                    stock.dividend_tier if hasattr(stock, "dividend_tier") else "N/A",
                ],
                [
                    "P/E Ratio",
                    self._fmt_number(stock.trailing_pe),
                    "Forward P/E",
                    self._fmt_number(stock.forward_pe),
                ],
                [
                    "Payout Ratio",
                    self._fmt_percent(stock.payout_ratio_pct),
                    "FCF Payout",
                    self._fmt_percent(stock.fcf_payout_ratio_pct) if stock.fcf_payout_ratio_pct else "N/A",
                ],
            ]
            
            table = Table(data, colWidths=[1.5*inch, 1.3*inch, 1.5*inch, 1.3*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["header_bg"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), self.COLORS["header_text"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                ("BACKGROUND", (0, 2), (-1, 2), self.COLORS["section_bg"]),
                ("BACKGROUND", (0, 4), (-1, 4), self.COLORS["section_bg"]),
                ("BACKGROUND", (0, 6), (-1, 6), self.COLORS["section_bg"]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 12))
            
            return elements
        
        def _build_dividend_analysis(self, stock: "StockData") -> List:
            """Build dividend analysis section."""
            elements = []
            
            elements.append(Paragraph("DIVIDEND ANALYSIS", self.styles["SectionHeader"]))
            
            dh = stock.dividend_history
            
            data = [
                ["Dividend Growth Rates", "", "Dividend Safety", ""],
                [
                    "DGR 10-Year",
                    self._fmt_percent(dh.cagr_10y) if dh and dh.cagr_10y else "N/A",
                    "Payout Ratio",
                    self._fmt_percent(stock.payout_ratio_pct),
                ],
                [
                    "DGR 5-Year",
                    self._fmt_percent(dh.cagr_5y) if dh and dh.cagr_5y else "N/A",
                    "FCF Payout",
                    self._fmt_percent(stock.fcf_payout_ratio_pct) if stock.fcf_payout_ratio_pct else "N/A",
                ],
                [
                    "Last Increase",
                    self._fmt_percent(dh.cagr_5y / 5) if dh and dh.cagr_5y else "N/A",
                    "Div Coverage",
                    self._fmt_number(stock.dividend_coverage) if stock.dividend_coverage else "N/A",
                ],
                [
                    "Consecutive Years",
                    str(dh.consecutive_years) if dh else "N/A",
                    "Safety Score",
                    f"{stock.dividend_safety_score:.0f}/100" if hasattr(stock, "dividend_safety_score") and stock.dividend_safety_score else "N/A",
                ],
            ]
            
            table = Table(data, colWidths=[1.5*inch, 1.3*inch, 1.5*inch, 1.3*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["header_bg"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), self.COLORS["header_text"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                ("BACKGROUND", (0, 2), (-1, 2), self.COLORS["section_bg"]),
                ("BACKGROUND", (0, 4), (-1, 4), self.COLORS["section_bg"]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 12))
            
            # Yield channels
            if stock.dividend_yield_pct:
                sp_yield = 1.32
                
                channel_data = [
                    ["Dividend Yield Channels", ""],
                    ["Current Yield", self._fmt_percent(stock.dividend_yield_pct)],
                    ["S&P 500 Yield", f"{sp_yield:.2f}%"],
                    ["Yield vs S&P", self._fmt_delta(stock.dividend_yield_pct - sp_yield)],
                ]
                
                channel_table = Table(channel_data, colWidths=[2*inch, 1.5*inch])
                channel_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["header_bg"]),
                    ("TEXTCOLOR", (0, 0), (-1, 0), self.COLORS["header_text"]),
                    ("SPAN", (0, 0), (-1, 0)),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                
                elements.append(channel_table)
                elements.append(Spacer(1, 12))
            
            return elements
        
        def _build_valuation(self, stock: "StockData") -> List:
            """Build valuation section."""
            elements = []
            
            elements.append(Paragraph("VALUATION ANALYSIS", self.styles["SectionHeader"]))
            
            current_price = stock.price or 0
            
            avg_pe = 20
            eps = current_price / stock.trailing_pe if stock.trailing_pe and stock.trailing_pe > 0 else 0
            pe_price = eps * avg_pe if eps else None
            
            target_yield = 3.0
            div_price = (stock.dividend_rate / (target_yield / 100)) if stock.dividend_rate and target_yield else None
            
            price_vs_high = stock.price_to_52w_high_pct if hasattr(stock, "price_to_52w_high_pct") else None
            
            data = [
                ["Valuation Metric", "Value", "Est. Price", "vs Current"],
                [
                    "P/E Ratio",
                    self._fmt_number(stock.trailing_pe),
                    self._fmt_currency(pe_price),
                    self._fmt_delta_pct((pe_price / current_price - 1) * 100) if pe_price and current_price else "N/A",
                ],
                [
                    "Forward P/E",
                    self._fmt_number(stock.forward_pe),
                    "N/A",
                    "N/A",
                ],
                [
                    "Dividend Yield Price",
                    f"@ {target_yield}% yield",
                    self._fmt_currency(div_price),
                    self._fmt_delta_pct((div_price / current_price - 1) * 100) if div_price and current_price else "N/A",
                ],
                [
                    "Price/Book",
                    self._fmt_number(stock.price_to_book),
                    "N/A",
                    "N/A",
                ],
                [
                    "Price to 52W High",
                    self._fmt_percent(price_vs_high) if price_vs_high else "N/A",
                    "N/A",
                    "N/A",
                ],
            ]
            
            table = Table(data, colWidths=[1.6*inch, 1.2*inch, 1.2*inch, 1.2*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["header_bg"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), self.COLORS["header_text"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("BACKGROUND", (0, 2), (-1, 2), self.COLORS["section_bg"]),
                ("BACKGROUND", (0, 4), (-1, 4), self.COLORS["section_bg"]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 12))
            
            # Financial strength metrics
            strength_data = [
                ["Financial Strength", "Value", "Rating"],
                [
                    "Debt/Equity",
                    self._fmt_number(stock.debt_to_equity),
                    self._rate_debt(stock.debt_to_equity),
                ],
                [
                    "Current Ratio",
                    self._fmt_number(stock.current_ratio),
                    self._rate_current_ratio(stock.current_ratio),
                ],
                [
                    "ROE",
                    self._fmt_percent(stock.roe_pct),
                    self._rate_roe(stock.roe_pct),
                ],
                [
                    "Operating Margin",
                    self._fmt_percent(stock.operating_margin_pct),
                    self._rate_margin(stock.operating_margin_pct),
                ],
            ]
            
            strength_table = Table(strength_data, colWidths=[2*inch, 1.5*inch, 1*inch])
            strength_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["header_bg"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), self.COLORS["header_text"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 2), (-1, 2), self.COLORS["section_bg"]),
                ("BACKGROUND", (0, 4), (-1, 4), self.COLORS["section_bg"]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            
            elements.append(strength_table)
            elements.append(Spacer(1, 12))
            
            return elements
        
        def _build_thesis(self, pros: List[str], cons: List[str]) -> List:
            """Build investment thesis section."""
            elements = []
            
            elements.append(Paragraph("INVESTMENT THESIS", self.styles["SectionHeader"]))
            
            elements.append(Paragraph("<b>Strengths:</b>", self.styles["Normal"]))
            
            for pro in pros[:5]:
                elements.append(Paragraph(f"  * {pro}", self.styles["ScorePositive"]))
            
            elements.append(Spacer(1, 6))
            
            elements.append(Paragraph("<b>Concerns:</b>", self.styles["Normal"]))
            
            for con in cons[:5]:
                elements.append(Paragraph(f"  * {con}", self.styles["ScoreNegative"]))
            
            elements.append(Spacer(1, 12))
            
            return elements
        
        def _build_financials(
            self,
            stock: "StockData",
            historical: Dict[str, Any],
        ) -> List:
            """Build financial data section (multi-year)."""
            elements = []
            
            elements.append(Paragraph("FINANCIAL DATA (Millions)", self.styles["SectionHeader"]))
            
            elements.append(Paragraph(
                "Note: Historical financial data requires data ingestion from external sources.",
                self.styles["Normal"]
            ))
            
            elements.append(Spacer(1, 12))
            
            return elements
        
        def _build_footer(self, stock: "StockData") -> List:
            """Build report footer with disclaimers."""
            elements = []
            
            elements.append(Spacer(1, 24))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
            elements.append(Spacer(1, 6))
            
            disclaimer = (
                "<b>DISCLAIMER:</b> This report is for educational purposes only and does not "
                "constitute financial advice. Past performance is not indicative of future results. "
                "Always conduct your own research and consult with a qualified financial advisor "
                "before making investment decisions."
            )
            
            elements.append(Paragraph(disclaimer, ParagraphStyle(
                name="Footer",
                parent=self.styles["Normal"],
                fontSize=7,
                textColor=colors.grey,
            )))
            
            sources = (
                f"<b>Data Sources:</b> Market Data Aggregator, Public Financial Filings. "
                f"Report generated by Dividend Kings Analyzer on {datetime.now().strftime('%Y-%m-%d %H:%M')}."
            )
            
            elements.append(Paragraph(sources, ParagraphStyle(
                name="Sources",
                parent=self.styles["Normal"],
                fontSize=7,
                textColor=colors.grey,
            )))
            
            return elements
        
        # Formatting helpers - delegate to shared utils
        def _fmt_currency(self, value: Optional[float]) -> str:
            return format_currency(value)
        
        def _fmt_percent(self, value: Optional[float]) -> str:
            return format_percent(value, decimals=2)
        
        def _fmt_number(self, value: Optional[float]) -> str:
            return format_number(value, decimals=2)
        
        def _fmt_market_cap(self, value: Optional[float]) -> str:
            return format_large_number(value)
        
        def _fmt_delta(self, value: float) -> str:
            return format_delta(value)
        
        def _fmt_delta_pct(self, value: Optional[float]) -> str:
            return format_delta_pct(value)
        
        # Rating helpers
        def _rate_debt(self, value: Optional[float]) -> str:
            if value is None:
                return "N/A"
            if value < 0.5:
                return "Excellent"
            if value < 1.0:
                return "Good"
            if value < 2.0:
                return "Fair"
            return "High"
        
        def _rate_current_ratio(self, value: Optional[float]) -> str:
            if value is None:
                return "N/A"
            if value >= 2.0:
                return "Strong"
            if value >= 1.5:
                return "Good"
            if value >= 1.0:
                return "Fair"
            return "Weak"
        
        def _rate_roe(self, value: Optional[float]) -> str:
            if value is None:
                return "N/A"
            if value >= 20:
                return "Excellent"
            if value >= 15:
                return "Good"
            if value >= 10:
                return "Fair"
            return "Low"
        
        def _rate_margin(self, value: Optional[float]) -> str:
            if value is None:
                return "N/A"
            if value >= 25:
                return "Excellent"
            if value >= 15:
                return "Good"
            if value >= 10:
                return "Fair"
            return "Low"

    def generate_stock_report(
        stock: "StockData",
        score: int,
        recommendation: str,
        pros: List[str],
        cons: List[str],
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Convenience function to generate a PDF report.
        
        Args:
            stock: StockData object.
            score: Investment score.
            recommendation: Recommendation label.
            pros: List of strengths.
            cons: List of concerns.
            output_path: Optional file path to save PDF.
            
        Returns:
            PDF as bytes.
        """
        generator = ReportGenerator()
        pdf_bytes = generator.generate(
            stock=stock,
            score=score,
            recommendation=recommendation,
            pros=pros,
            cons=cons,
        )
        
        if output_path:
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
            logger.info(f"Report saved to {output_path}")
        
        return pdf_bytes

else:
    # Stub classes when reportlab is not available
    class ReportGenerator:
        """Stub class when reportlab is not installed."""
        
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "reportlab required for PDF generation. "
                "Install with: pip install reportlab"
            )
    
    def generate_stock_report(*args, **kwargs) -> bytes:
        """Stub function when reportlab is not installed."""
        raise ImportError(
            "reportlab required for PDF generation. "
            "Install with: pip install reportlab"
        )
