"""
DividendScope design system — fintech dashboard styling for Streamlit.

Reusable HTML/CSS components and global theme tokens. No business logic.
"""

from __future__ import annotations

import html
from typing import Literal

import streamlit as st

PRODUCT_NAME = "DividendScope"

StatusKind = Literal[
    "healthy",
    "watch",
    "risky",
    "unknown",
    "confirmed",
    "estimated",
    "missing",
]

_STATUS_CLASS: dict[str, str] = {
    "Healthy": "healthy",
    "Watch": "watch",
    "Risky": "risky",
    "Not enough data": "unknown",
    "Confirmed": "confirmed",
    "Estimated": "estimated",
    "Missing": "missing",
    "Not available yet": "missing",
}

LOGO_SVG = """
<svg class="ds-logo-svg" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="dsLogoGrad" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#0f766e"/>
      <stop offset="100%" stop-color="#14b8a6"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="36" height="36" rx="10" fill="url(#dsLogoGrad)"/>
  <path d="M12 28V12h8.5c4.2 0 6.8 2.2 6.8 5.6 0 2.4-1.3 4.1-3.4 4.9 2.8.7 4.4 2.6 4.4 5.5 0 3.8-3 6-8.2 6H12zm5.2-10.2h3.1c1.8 0 2.8-.9 2.8-2.4s-1-2.3-2.9-2.3h-3v4.7zm0 8.4h3.6c2.1 0 3.3-1 3.3-2.7 0-1.7-1.2-2.6-3.4-2.6h-3.2v5.3z" fill="#fff"/>
  <circle cx="30" cy="11" r="2.5" fill="#fef08a"/>
  <path d="M30 13.5v8" stroke="#fef08a" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M27 18.5l3-3 3 3" stroke="#fef08a" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>
"""

DESIGN_SYSTEM_CSS = """
:root {
  --ds-primary: #2dd4bf;
  --ds-primary-dark: #14b8a6;
  --ds-primary-light: #5eead4;
  --ds-accent: #38bdf8;
  --ds-bg: #0b1220;
  --ds-bg-elevated: #0f172a;
  --ds-surface: #131c2e;
  --ds-surface-elevated: #1a2740;
  --ds-border: #2a3a52;
  --ds-border-subtle: #1e293b;
  --ds-text: #e8eef7;
  --ds-muted: #94a3b8;
  --ds-highlight-bg: rgba(45, 212, 191, 0.1);
  --ds-highlight-border: rgba(45, 212, 191, 0.5);
  --ds-highlight-glow: 0 0 0 1px rgba(45, 212, 191, 0.25), 0 8px 28px rgba(45, 212, 191, 0.12);
  --ds-radius: 12px;
  --ds-radius-sm: 8px;
  --ds-shadow: 0 1px 3px rgba(0, 0, 0, 0.35), 0 4px 18px rgba(0, 0, 0, 0.25);
  --ds-shadow-lg: 0 10px 36px rgba(0, 0, 0, 0.45);
  --ds-focus: 0 0 0 3px rgba(45, 212, 191, 0.4);
}

.stApp {
  background: linear-gradient(180deg, #070d18 0%, var(--ds-bg) 160px, var(--ds-bg) 100%) !important;
  color: var(--ds-text);
}

[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main {
  background: transparent !important;
}

[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stCaptionContainer"] p {
  color: inherit;
}

/* Focus & accessibility */
.stButton button:focus-visible,
.stTextInput input:focus-visible,
.stNumberInput input:focus-visible,
.stSelectbox div[data-baseweb="select"]:focus-within {
  outline: none !important;
  box-shadow: var(--ds-focus) !important;
}

/* Logo & brand */
.ds-brand-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin: 0 0 1rem 0;
  padding: 0.15rem 0;
}
.ds-logo-svg {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}
.ds-brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}
.ds-brand-name {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--ds-text);
  letter-spacing: -0.02em;
}
.ds-brand-tagline {
  font-size: 0.72rem;
  color: var(--ds-muted);
  font-weight: 500;
}

/* Badges */
.ds-beta-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: rgba(45, 212, 191, 0.12);
  color: #5eead4;
  border: 1px solid rgba(45, 212, 191, 0.35);
  border-radius: 999px;
  padding: 0.22rem 0.7rem;
  font-size: 0.72rem;
  font-weight: 650;
  letter-spacing: 0.02em;
  margin-bottom: 0.65rem;
}
.ds-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
}
.ds-status-badge::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ds-status-healthy { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.35); }
.ds-status-healthy::before { background: #34d399; }
.ds-status-watch { background: rgba(245, 158, 11, 0.12); color: #fcd34d; border: 1px solid rgba(251, 191, 36, 0.35); }
.ds-status-watch::before { background: #fbbf24; }
.ds-status-risky { background: rgba(239, 68, 68, 0.12); color: #fca5a5; border: 1px solid rgba(248, 113, 113, 0.35); }
.ds-status-risky::before { background: #f87171; }
.ds-status-unknown { background: rgba(148, 163, 184, 0.1); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.25); }
.ds-status-unknown::before { background: #94a3b8; }
.ds-status-confirmed { background: rgba(59, 130, 246, 0.12); color: #93c5fd; border: 1px solid rgba(96, 165, 250, 0.35); }
.ds-status-confirmed::before { background: #60a5fa; }
.ds-status-estimated { background: rgba(168, 85, 247, 0.12); color: #d8b4fe; border: 1px solid rgba(192, 132, 252, 0.35); }
.ds-status-estimated::before { background: #c084fc; }
.ds-status-missing { background: rgba(100, 116, 139, 0.12); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.3); }
.ds-status-missing::before { background: #64748b; }

/* Section headers */
.ds-section-header {
  margin: 0 0 0.85rem 0;
}
.ds-section-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 650;
  color: var(--ds-text);
  letter-spacing: -0.02em;
}
.ds-section-subtitle {
  margin: 0.25rem 0 0 0;
  font-size: 0.88rem;
  color: var(--ds-muted);
  line-height: 1.45;
}

/* Cards */
.ds-card {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  box-shadow: var(--ds-shadow);
  padding: 1rem 1.1rem;
  margin-bottom: 0.85rem;
}
.ds-card-elevated {
  box-shadow: var(--ds-shadow-lg);
  border-color: rgba(15, 118, 110, 0.15);
}
.ds-metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem;
}
@media (min-width: 640px) {
  .ds-metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.ds-metric-card {
  background: linear-gradient(180deg, var(--ds-surface-elevated) 0%, var(--ds-surface) 100%);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-sm);
  padding: 0.65rem 0.75rem;
  min-height: 4.5rem;
  transition: box-shadow 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ds-metric-card:hover {
  box-shadow: var(--ds-shadow);
  border-color: rgba(45, 212, 191, 0.35);
  transform: translateY(-1px);
}
.ds-metric-card.ds-highlight {
  background: linear-gradient(145deg, rgba(45, 212, 191, 0.14) 0%, var(--ds-surface-elevated) 55%);
  border-color: var(--ds-highlight-border);
  box-shadow: var(--ds-highlight-glow);
}
.ds-metric-card.ds-highlight .ds-metric-label {
  color: var(--ds-primary-light);
}
.ds-metric-card.ds-highlight .ds-metric-value {
  color: #f0fdfa;
}
.ds-metric-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ds-muted);
  margin: 0 0 0.25rem 0;
}
.ds-metric-value {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--ds-text);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.ds-metric-hint {
  font-size: 0.72rem;
  color: var(--ds-muted);
  margin: 0.2rem 0 0 0;
}

/* Chart card */
.ds-chart-card {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  padding: 0.85rem 0.85rem 0.25rem;
  margin: 0.5rem 0 1rem 0;
  overflow: hidden;
}
.ds-chart-card-title {
  margin: 0 0 0.15rem 0;
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--ds-text);
}
.ds-chart-card-subtitle {
  margin: 0 0 0.65rem 0;
  font-size: 0.8rem;
  color: var(--ds-muted);
}

/* Empty state */
.ds-empty-state {
  text-align: center;
  padding: 2rem 1.25rem;
  background: var(--ds-surface);
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius);
  margin: 0.75rem 0 1rem 0;
}
.ds-empty-icon {
  font-size: 1.75rem;
  margin-bottom: 0.5rem;
  opacity: 0.85;
}
.ds-empty-title {
  margin: 0 0 0.35rem 0;
  font-size: 1rem;
  font-weight: 650;
  color: var(--ds-text);
}
.ds-empty-body {
  margin: 0;
  font-size: 0.88rem;
  color: var(--ds-muted);
  line-height: 1.45;
  max-width: 28rem;
  margin-left: auto;
  margin-right: auto;
}

/* Disclaimer & footer */
.ds-disclaimer-banner {
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.08), rgba(19, 28, 46, 0.9));
  border: 1px solid rgba(45, 212, 191, 0.28);
  border-left: 4px solid var(--ds-primary);
  border-radius: var(--ds-radius-sm);
  padding: 0.65rem 0.85rem;
  font-size: 0.82rem;
  color: #cbd5e1;
  line-height: 1.45;
  margin: 0.75rem 0;
}
.ds-app-footer {
  margin-top: 2rem;
  padding: 1.25rem 0 0.5rem;
  border-top: 1px solid var(--ds-border);
  font-size: 0.78rem;
  color: var(--ds-muted);
  line-height: 1.5;
}
.ds-footer-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 1.25rem;
  margin-bottom: 0.5rem;
}
.ds-footer-links span {
  color: var(--ds-primary);
  font-weight: 600;
}

/* Health panel */
.ds-health-panel {
  border-radius: var(--ds-radius-sm);
  padding: 0.85rem 1rem;
  margin: 0.5rem 0 1rem 0;
  line-height: 1.45;
}
.ds-health-panel-title {
  font-size: 0.95rem;
  font-weight: 650;
  margin: 0 0 0.35rem 0;
}
.ds-health-panel-body {
  font-size: 0.85rem;
  color: var(--ds-muted);
  margin: 0;
}

/* Dividend focus — high-interest strip */
.ds-dividend-focus {
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.08) 0%, var(--ds-surface) 40%, var(--ds-surface) 100%);
  border: 1px solid var(--ds-highlight-border);
  border-radius: var(--ds-radius);
  padding: 1rem 1.1rem 0.85rem;
  margin: 0 0 1rem 0;
  box-shadow: var(--ds-highlight-glow);
  position: relative;
  overflow: hidden;
}
.ds-dividend-focus::before {
  content: "DIVIDEND FOCUS";
  position: absolute;
  top: 0.65rem;
  right: 0.85rem;
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  color: var(--ds-primary-light);
  opacity: 0.85;
}
.ds-dividend-section {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  padding: 1rem 1.1rem 0.25rem;
  margin: 0.5rem 0 1rem 0;
  box-shadow: var(--ds-shadow);
}

/* Tables */
.ds-table-wrap {
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 0.5rem 0 1rem 0;
  background: var(--ds-surface);
  box-shadow: var(--ds-shadow);
}
[data-testid="stDataFrame"] div[data-testid="StyledFullScreenFrame"] {
  border: none !important;
  border-radius: 0 !important;
}
[data-testid="stDataFrame"] [role="columnheader"] {
  background: var(--ds-surface-elevated) !important;
  font-size: 0.72rem !important;
  font-weight: 650 !important;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--ds-muted) !important;
}
[data-testid="stDataFrame"] [role="gridcell"] {
  font-variant-numeric: tabular-nums;
  font-size: 0.85rem;
  background: var(--ds-surface) !important;
  color: var(--ds-text) !important;
}
[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {
  background: rgba(45, 212, 191, 0.06) !important;
}

/* Command Center hero */
.cc-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.25rem;
  margin-bottom: 0.5rem;
}
@media (min-width: 900px) {
  .cc-layout { grid-template-columns: 1.05fr 0.95fr; align-items: start; }
}
.cc-hero {
  text-align: left;
  padding: 0.5rem 0 1rem;
}
.cc-hero-eyebrow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.75rem 0;
}
.cc-hero-title {
  font-size: clamp(1.65rem, 4vw, 2.15rem);
  font-weight: 750;
  line-height: 1.15;
  margin: 0 0 0.85rem 0;
  color: var(--ds-text);
  letter-spacing: -0.03em;
}
.cc-hero-sub {
  font-size: 1.02rem;
  color: var(--ds-muted);
  max-width: 36rem;
  margin: 0 0 1.25rem 0;
  line-height: 1.55;
}
.cc-preview-card {
  background: linear-gradient(160deg, var(--ds-surface-elevated) 0%, rgba(45, 212, 191, 0.06) 45%, var(--ds-surface) 100%);
  border: 1px solid var(--ds-highlight-border);
  border-radius: var(--ds-radius);
  box-shadow: var(--ds-highlight-glow);
  padding: 1rem 1.1rem 0.85rem;
  position: relative;
  overflow: hidden;
}
.cc-preview-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--ds-primary), var(--ds-primary-light));
}
.cc-preview-label {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ds-primary);
  margin: 0 0 0.65rem 0;
}
.cc-sparkline {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 48px;
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--ds-border);
}
.cc-spark-bar {
  flex: 1;
  min-width: 4px;
  background: linear-gradient(180deg, var(--ds-primary-light), var(--ds-primary));
  border-radius: 2px 2px 0 0;
  opacity: 0.85;
}
.cc-alert-row {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  font-size: 0.78rem;
  color: #475569;
  margin: 0.35rem 0 0;
  line-height: 1.35;
}

/* Dividend section card — merged above */

/* Feedback */
.ds-feedback-trigger {
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-sm);
  padding: 0.15rem 0;
  background: rgba(255,255,255,0.6);
}

/* Typography & motion */
.stApp, [data-testid="stMarkdownContainer"] {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Sidebar polish */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, var(--ds-bg-elevated) 0%, var(--ds-bg) 100%) !important;
  border-right: 1px solid var(--ds-border);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] .ds-brand-name {
  color: var(--ds-text) !important;
}
[data-testid="stSidebar"] .ds-brand-tagline,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
  color: var(--ds-muted) !important;
}
[data-testid="stSidebar"] .stButton button {
  border-radius: 10px !important;
  font-weight: 600 !important;
  transition: transform 0.12s ease, box-shadow 0.12s ease !important;
}
[data-testid="stSidebar"] .stButton button:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(15, 118, 110, 0.12);
}

/* Main panel buttons */
[data-testid="stMain"] .stButton button {
  border-radius: 10px !important;
  font-weight: 600 !important;
  transition: transform 0.12s ease, box-shadow 0.12s ease !important;
}
[data-testid="stMain"] .stButton button:hover {
  transform: translateY(-1px);
}
[data-testid="stMain"] .stButton button[kind="primary"],
[data-testid="stMain"] .stButton button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%) !important;
  border: none !important;
  box-shadow: 0 2px 14px rgba(45, 212, 191, 0.28) !important;
  color: #042f2e !important;
}
[data-testid="stMain"] .stButton button[kind="secondary"],
[data-testid="stMain"] .stButton button[data-testid="stBaseButton-secondary"] {
  background: var(--ds-surface-elevated) !important;
  border: 1px solid var(--ds-border) !important;
  color: var(--ds-text) !important;
}

/* Streamlit metrics — dark surfaces */
div[data-testid="stMetric"] {
  background: var(--ds-surface) !important;
  border: 1px solid var(--ds-border) !important;
  border-radius: 10px !important;
}
div[data-testid="stMetric"] label,
div[data-testid="stMetric"] label p {
  color: var(--ds-muted) !important;
}
div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] p {
  color: var(--ds-text) !important;
}
div[data-testid="stMetric"].ds-metric-dividend-highlight {
  border-color: var(--ds-highlight-border) !important;
  box-shadow: var(--ds-highlight-glow) !important;
  background: linear-gradient(145deg, rgba(45, 212, 191, 0.12), var(--ds-surface)) !important;
}
div[data-testid="stMetric"].ds-metric-dividend-highlight label,
div[data-testid="stMetric"].ds-metric-dividend-highlight label p {
  color: var(--ds-primary-light) !important;
}

/* Expanders & inputs */
[data-testid="stExpander"] {
  border: 1px solid var(--ds-border) !important;
  border-radius: var(--ds-radius-sm) !important;
  background: var(--ds-surface) !important;
  box-shadow: var(--ds-shadow);
}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
  border-radius: 10px !important;
  border-color: var(--ds-border) !important;
  background: var(--ds-surface-elevated) !important;
  color: var(--ds-text) !important;
}
[data-testid="stAlert"] {
  background: var(--ds-surface) !important;
  border-color: var(--ds-border) !important;
}

/* Plotly in chart cards */
.ds-chart-card [data-testid="stPlotlyChart"] {
  margin: 0 -0.25rem -0.25rem;
}

/* Yield channel panel + Plotly on dark dashboard */
.ds-yield-channel-panel {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  padding: 0.85rem;
  margin: 0.5rem 0 0.35rem 0;
  box-shadow: var(--ds-shadow);
}
.ds-yield-channel-panel .ds-section-header {
  margin-bottom: 0.55rem;
}
.ds-yield-channel-panel .ds-metric-grid {
  margin: 0.75rem 0 0;
}
.ds-yield-channel-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem 1rem;
  margin: 0.15rem 0 0;
  padding-left: 0.85rem;
  border-left: 4px solid var(--ds-primary);
}
.ds-yield-zone-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-weight: 650;
  font-size: 0.92rem;
  padding: 0.22rem 0.62rem;
  border-radius: 999px;
  border: 1px solid;
  background: rgba(15, 23, 42, 0.72);
}
.ds-yield-channel-meta .ds-yield-zone-sub {
  margin: 0;
  font-size: 0.84rem;
  color: var(--ds-muted);
}
[data-testid="stPlotlyChart"] {
  background: var(--ds-surface) !important;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  overflow: hidden;
  margin: 0 0 1rem 0;
  box-shadow: var(--ds-shadow);
}
[data-testid="stPlotlyChart"] .js-plotly-plot,
[data-testid="stPlotlyChart"] .plot-container {
  background: transparent !important;
}

/* Feature cards */
.ds-feature-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
  margin: 0.5rem 0 1rem;
}
@media (min-width: 768px) {
  .ds-feature-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.ds-feature-card {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  padding: 1.15rem 1rem;
  box-shadow: var(--ds-shadow);
  transition: box-shadow 0.18s ease, transform 0.18s ease, border-color 0.18s ease;
  height: 100%;
}
.ds-feature-card:hover {
  box-shadow: var(--ds-shadow-lg);
  transform: translateY(-2px);
  border-color: rgba(45, 212, 191, 0.35);
}
.ds-feature-icon {
  font-size: 1.45rem;
  margin-bottom: 0.55rem;
  line-height: 1;
}
.ds-feature-title {
  font-weight: 650;
  font-size: 0.95rem;
  color: var(--ds-text);
  margin: 0 0 0.4rem 0;
}
.ds-feature-body {
  font-size: 0.84rem;
  color: var(--ds-muted);
  line-height: 1.5;
  margin: 0;
}

/* Ticker chips */
.ds-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.65rem 0;
}
.ds-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: rgba(45, 212, 191, 0.1);
  border: 1px solid rgba(45, 212, 191, 0.35);
  color: #99f6e4;
  border-radius: 999px;
  padding: 0.38rem 0.85rem;
  font-size: 0.82rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

/* Payout rows */
.ds-list-card {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-sm);
  padding: 0.35rem 0.85rem;
  margin: 0.5rem 0 1rem;
}
.ds-payout-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.84rem;
  color: var(--ds-text);
}
.ds-payout-row:last-child { border-bottom: none; }
.ds-payout-meta { color: var(--ds-muted); font-size: 0.78rem; }

/* Panels */
.ds-panel {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  padding: 1rem 1.1rem 0.85rem;
  margin: 0.65rem 0 1rem;
  box-shadow: var(--ds-shadow);
}
.ds-portfolio-nav-section {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius);
  padding: 1rem 1rem 0.5rem;
  margin: 1rem 0;
  box-shadow: var(--ds-shadow);
}
.ds-portfolio-nav-section .stButton button {
  min-height: 2.5rem;
}

/* Yield zone headline */
.ds-yield-zone {
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
  line-height: 1.2;
}
.ds-yield-zone-sub {
  color: var(--ds-muted);
  font-size: 0.88rem;
  margin: 0.2rem 0 0;
  line-height: 1.35;
}

/* Accent text in hero */
.cc-hero-title .ds-accent {
  background: linear-gradient(135deg, #5eead4 0%, #2dd4bf 45%, #38bdf8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.cc-preview-card::after {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 100% 0%, rgba(45, 212, 191, 0.12), transparent 55%);
  pointer-events: none;
}

/* Page divider */
.ds-page-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--ds-border), transparent);
  margin: 1.75rem 0;
  border: none;
}

/* Section label overline */
.ds-overline {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ds-primary);
  margin: 0 0 0.35rem 0;
}

/* Delta colors on metrics */
div[data-testid="stMetricDelta"] svg { display: none; }
div[data-testid="stMetricDelta"][data-test-direction="up"] {
  color: #6ee7b7 !important;
}
div[data-testid="stMetricDelta"][data-test-direction="down"] {
  color: #fca5a5 !important;
}

/* Yield zone accent bar on chart sections */
.ds-yield-zone-wrap {
  border-left: 4px solid var(--ds-primary);
  padding-left: 0.85rem;
  margin: 0.25rem 0 0.75rem;
}
"""


def render_html(markup: str, *, sidebar: bool = False) -> None:
    """Render raw HTML without Markdown parsing (avoids indented blocks showing as code)."""
    target = st.sidebar if sidebar else st
    target.html(markup)


def _section_header_markup(title: str, subtitle: str = "") -> str:
    sub = f'<p class="ds-section-subtitle">{html.escape(subtitle)}</p>' if subtitle else ""
    return (
        f'<div class="ds-section-header">'
        f'<h3 class="ds-section-title">{html.escape(title)}</h3>{sub}'
        f"</div>"
    )


def _metric_card_markup(
    label: str,
    value: str,
    hint: str = "",
    *,
    highlight: bool = False,
) -> str:
    cls = "ds-metric-card ds-highlight" if highlight else "ds-metric-card"
    hint_html = f'<p class="ds-metric-hint">{html.escape(hint)}</p>' if hint else ""
    return (
        f'<div class="{cls}">'
        f'<p class="ds-metric-label">{html.escape(label)}</p>'
        f'<p class="ds-metric-value">{html.escape(value)}</p>'
        f"{hint_html}"
        f"</div>"
    )


def _health_panel_markup(label: str, reasons: tuple[str, ...] | list[str]) -> str:
    kind = status_class_for_label(label)
    dark_colors = {
        "healthy": ("rgba(16, 185, 129, 0.12)", "#6ee7b7", "rgba(52, 211, 153, 0.35)"),
        "watch": ("rgba(245, 158, 11, 0.1)", "#fcd34d", "rgba(251, 191, 36, 0.35)"),
        "risky": ("rgba(239, 68, 68, 0.1)", "#fca5a5", "rgba(248, 113, 113, 0.35)"),
        "unknown": ("rgba(148, 163, 184, 0.08)", "#cbd5e1", "rgba(148, 163, 184, 0.25)"),
    }
    bg, fg, border = dark_colors.get(kind, dark_colors["unknown"])
    reason_text = html.escape(" · ".join(reasons[:3]) if reasons else "")
    return (
        f'<div class="ds-health-panel" style="background:{bg};border:1px solid {border};color:{fg};">'
        f'<p class="ds-health-panel-title">Dividend health · {html.escape(label)}</p>'
        f'<p class="ds-health-panel-body">{reason_text}</p>'
        f"</div>"
    )


def _metric_grid_markup(
    items: list[tuple[str, str, str] | tuple[str, str, str, bool]],
    *,
    highlight_all: bool = False,
) -> str:
    cards = []
    for item in items:
        if len(item) >= 4:
            label, value, hint, highlighted = item[0], item[1], item[2], bool(item[3])
        else:
            label, value, hint = item[0], item[1], item[2]
            highlighted = highlight_all
        cards.append(_metric_card_markup(label, value, hint, highlight=highlighted))
    return f'<div class="ds-metric-grid">{"".join(cards)}</div>'


def render_page_divider() -> None:
    render_html('<hr class="ds-page-divider" aria-hidden="true">')


def open_dividend_focus_panel() -> None:
    """Deprecated: use render_dividend_focus_panel instead."""


def close_dividend_focus_panel() -> None:
    """Deprecated: use render_dividend_focus_panel instead."""


def open_panel() -> None:
    """Deprecated: Streamlit widgets cannot be wrapped by split HTML tags."""


def close_panel() -> None:
    """Deprecated: Streamlit widgets cannot be wrapped by split HTML tags."""


def render_dividend_focus_panel(
    title: str,
    subtitle: str,
    metrics: list[tuple[str, str, str] | tuple[str, str, str, bool]],
) -> None:
    """Single HTML block for the dividend income highlight panel."""
    render_html(
        f'<div class="ds-dividend-focus">'
        f"{_section_header_markup(title, subtitle)}"
        f"{_metric_grid_markup(metrics)}"
        f"</div>"
    )


def render_feature_cards(cards: list[tuple[str, str, str]]) -> None:
    """Render icon + title + body feature cards."""
    items = "".join(
        f'<div class="ds-feature-card">'
        f'<div class="ds-feature-icon" aria-hidden="true">{html.escape(icon)}</div>'
        f'<p class="ds-feature-title">{html.escape(title)}</p>'
        f'<p class="ds-feature-body">{html.escape(body)}</p>'
        f"</div>"
        for icon, title, body in cards
    )
    render_html(f'<div class="ds-feature-grid">{items}</div>')


def render_ticker_chips(items: list[tuple[str, str]]) -> None:
    """Render ticker chips: (symbol, detail)."""
    chips = "".join(
        f'<span class="ds-chip"><strong>{html.escape(symbol)}</strong> {html.escape(detail)}</span>'
        for symbol, detail in items
    )
    render_html(f'<div class="ds-chip-row">{chips}</div>')


def render_payout_list(rows: list[tuple[str, str, str]]) -> None:
    """Render payout rows: (symbol, amount, meta)."""
    body = "".join(
        f'<div class="ds-payout-row">'
        f"<span><strong>{html.escape(symbol)}</strong></span>"
        f'<span>{html.escape(amount)} <span class="ds-payout-meta">{html.escape(meta)}</span></span>'
        f"</div>"
        for symbol, amount, meta in rows
    )
    render_html(f'<div class="ds-list-card">{body}</div>')


def render_yield_zone_headline(zone: str, emoji: str, subtitle: str, *, color: str) -> None:
    render_html(
        f'<div class="ds-yield-zone-wrap">'
        f'<p class="ds-yield-zone" style="color:{html.escape(color)}">'
        f"{html.escape(emoji)} {html.escape(zone)}</p>"
        f'<p class="ds-yield-zone-sub">{html.escape(subtitle)}</p>'
        f"</div>"
    )


def render_yield_channel_summary(
    title: str,
    subtitle: str,
    *,
    zone: str,
    zone_emoji: str,
    zone_color: str,
    zone_detail: str,
    metrics: list[tuple[str, str, str] | tuple[str, str, str, bool]],
) -> None:
    """Header, zone chip, and key metrics for the yield channel chart block."""
    zone_chip = (
        f'<span class="ds-yield-zone-chip" style="border-color:{html.escape(zone_color)};'
        f'color:{html.escape(zone_color)}">'
        f"{html.escape(zone_emoji)} {html.escape(zone)}"
        f"</span>"
    )
    render_html(
        f'<div class="ds-yield-channel-panel">'
        f"{_section_header_markup(title, subtitle)}"
        f'<div class="ds-yield-channel-meta">{zone_chip}'
        f'<p class="ds-yield-zone-sub">{html.escape(zone_detail)}</p>'
        f"</div>"
        f"{_metric_grid_markup(metrics)}"
        f"</div>"
    )


def inject_design_system() -> None:
    """Inject global design-system CSS once per run."""
    render_html(f"<style>{DESIGN_SYSTEM_CSS}</style>")


def render_logo(*, show_name: bool = True, tagline: str = "Dividend research", sidebar: bool = False) -> None:
    beta_inline = (
        '<span class="ds-beta-badge" style="margin:0 0 0 0.35rem;vertical-align:middle;font-size:0.65rem">Beta</span>'
    )
    name_html = (
        f'<div class="ds-brand-text">'
        f'<span class="ds-brand-name">{html.escape(PRODUCT_NAME)}{beta_inline}</span>'
        f'<span class="ds-brand-tagline">{html.escape(tagline)}</span>'
        f"</div>"
        if show_name
        else ""
    )
    markup = (
        f'<div class="ds-brand-row" role="img" aria-label="{html.escape(PRODUCT_NAME)} logo">'
        f"{LOGO_SVG}{name_html}</div>"
    )
    render_html(markup, sidebar=sidebar)


def render_beta_badge(*, extra: str = "Free during beta") -> None:
    render_html(
        f'<span class="ds-beta-badge" aria-label="Beta version">{html.escape(extra)} · No credit card</span>'
    )


def status_class_for_label(label: str) -> str:
    return _STATUS_CLASS.get(label, "unknown")


def render_status_badge(label: str, *, title: str | None = None) -> None:
    kind = status_class_for_label(label)
    title_attr = f' title="{html.escape(title)}"' if title else ""
    render_html(
        f'<span class="ds-status-badge ds-status-{kind}"{title_attr}>{html.escape(label)}</span>'
    )


def render_section_header(title: str, subtitle: str = "") -> None:
    render_html(_section_header_markup(title, subtitle))


def render_metric_card(label: str, value: str, hint: str = "", *, highlight: bool = False) -> None:
    render_html(_metric_card_markup(label, value, hint, highlight=highlight))


def render_metric_grid(
    items: list[tuple[str, str, str] | tuple[str, str, str, bool]],
    *,
    highlight_all: bool = False,
) -> None:
    """Render a responsive grid of metric cards. Optional 4th tuple item = highlight."""
    render_html(_metric_grid_markup(items, highlight_all=highlight_all))


def render_empty_state(
    title: str,
    body: str,
    *,
    icon: str = "📊",
) -> None:
    render_html(
        f'<div class="ds-empty-state" role="status">'
        f'<div class="ds-empty-icon" aria-hidden="true">{html.escape(icon)}</div>'
        f'<p class="ds-empty-title">{html.escape(title)}</p>'
        f'<p class="ds-empty-body">{html.escape(body)}</p>'
        f"</div>"
    )


def render_chart_card_header(title: str, subtitle: str = "") -> None:
    sub = f'<p class="ds-chart-card-subtitle">{html.escape(subtitle)}</p>' if subtitle else ""
    render_html(
        f'<div class="ds-chart-card">'
        f'<p class="ds-chart-card-title">{html.escape(title)}</p>{sub}'
        f"</div>"
    )


def render_chart_card_footer() -> None:
    """No-op: chart card header is a self-contained block."""


def render_disclaimer_banner(message: str) -> None:
    render_html(f'<div class="ds-disclaimer-banner" role="note">{html.escape(message)}</div>')


def render_health_panel(label: str, reasons: tuple[str, ...] | list[str]) -> None:
    render_html(_health_panel_markup(label, reasons))


def render_dividend_detail_block(
    title: str,
    subtitle: str,
    health_label: str,
    reasons: tuple[str, ...] | list[str],
    metrics: list[tuple[str, str, str] | tuple[str, str, str, bool]],
) -> None:
    """Header, health, and metric grid in one HTML block for stock detail."""
    render_html(
        f'<div class="ds-dividend-section">'
        f"{_section_header_markup(title, subtitle)}"
        f"{_health_panel_markup(health_label, reasons)}"
        f"{_metric_grid_markup(metrics)}"
        f"</div>"
    )


def render_app_footer(*, show_pricing_hint: bool = True) -> None:
    pricing = (
        "<p>Free during beta · Planned Pro: $5/mo or $40/yr (no Stripe yet).</p>"
        if show_pricing_hint
        else ""
    )
    render_html(
        f'<footer class="ds-app-footer">'
        f'<div class="ds-footer-links">'
        f"<span>Disclaimer</span><span>Privacy</span><span>Terms</span><span>Feedback</span>"
        f"</div>"
        f"{pricing}"
        f"<p>{html.escape(PRODUCT_NAME)} — dividend tracking and research only. Not financial advice.</p>"
        f"</footer>"
    )


def wrap_table_container() -> None:
    """No-op: table styling is applied via global CSS on stDataFrame."""


def close_table_container() -> None:
    """No-op: table styling is applied via global CSS on stDataFrame."""


def sparkline_bars(values: list[float], *, max_height: int = 44) -> str:
    if not values:
        return ""
    peak = max(values) or 1.0
    bars = []
    for value in values:
        height = max(4, int((value / peak) * max_height))
        bars.append(f'<div class="cc-spark-bar" style="height:{height}px" title="${value:,.0f}"></div>')
    return f'<div class="cc-sparkline" aria-hidden="true">{"".join(bars)}</div>'
