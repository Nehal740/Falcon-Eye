FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code and documentation (the support assistant reads docs/*.md)
COPY *.py ./
COPY routers ./routers
COPY docs ./docs

RUN useradd --create-home --uid 10001 falconeye && chown -R falconeye /app
USER falconeye

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

# The database is created/upgraded automatically at start-up (see migrations.py).
# One worker on purpose: the rate limiter keeps its counters in memory.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
