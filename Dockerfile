FROM python:3.12-slim

RUN pip install --no-cache-dir pyyaml playwright && \
    playwright install --with-deps chromium && \
    playwright install-deps chromium

WORKDIR /app
COPY . .

ENV AV_CONFIG=/app/config.yaml

ENTRYPOINT ["python", "avscraper.py"]
CMD ["--help"]
