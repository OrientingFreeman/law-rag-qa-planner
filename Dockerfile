FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LAW_RAG_HOST=0.0.0.0 \
    LAW_RAG_PORT=8000 \
    LAW_RAG_RELOAD=false

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt pyproject.toml ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY law_rag ./law_rag
COPY data ./data
COPY domains ./domains
COPY evaluation ./evaluation
COPY prompts ./prompts
COPY README.md ./

RUN mkdir -p /app/logs /app/evaluation/reports && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "law_rag.api"]
