FROM python:3.12-slim

WORKDIR /app

# Dependances systeme minimales pour psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Durcissement (mise en production MSPR3) : execution en utilisateur non-root.
# MPLCONFIGDIR inscriptible pour matplotlib (backend Agg, generation des PNG d'eval).
ENV MPLCONFIGDIR=/tmp/matplotlib
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=8).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
