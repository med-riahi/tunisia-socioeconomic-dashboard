FROM python:3.12-slim

WORKDIR /app

# geopandas/rapidfuzz need a couple of system libs to build/run cleanly
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[app]"

COPY app ./app
COPY config ./config
COPY scripts ./scripts
COPY data ./data
COPY .streamlit ./.streamlit

EXPOSE 8501

# Default: serve the dashboard. The same image also runs the ETL job via:
#   docker run <image> python scripts/run_etl.py
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
