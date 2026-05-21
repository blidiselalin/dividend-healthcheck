FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DIVIDENDSCOPE_DATA_DIR=/data
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://127.0.0.1:8501/_stcore/health || exit 1

CMD [
  "streamlit", "run", "app.py",
  "--server.port=8501",
  "--server.address=0.0.0.0",
  "--server.headless=true",
  "--browser.gatherUsageStats=false",
  "--server.enableCORS=false",
  "--server.enableXsrfProtection=false"
]
