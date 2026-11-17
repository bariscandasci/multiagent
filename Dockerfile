FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
    && pip install --no-cache-dir --upgrade pip \
    && rm -rf /root/.cache /tmp/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pytest \
    && rm -rf /root/.cache /tmp/*

COPY --chown=appuser:appuser . .

# DejaVu gömülü PDF, imajda font dosyaları eksikse burada durur.
RUN python -c "from api.pdf_export import build_proposal_pdf; pdf = build_proposal_pdf('Deneme', {'executive': 'İstanbul — şğüöçı'}); assert pdf[:5] == b'%PDF' and len(pdf) > 800"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# Tek süreç. 0.0.0.0 yok; yalnız 127.0.0.1 ve BIND_IP.
CMD ["python", "-m", "deploy.private_server"]
