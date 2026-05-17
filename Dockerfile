FROM python:3.12-slim

RUN pip install --no-cache-dir pyyaml playwright flask gunicorn && \
    playwright install --with-deps chromium && \
    playwright install-deps chromium

WORKDIR /app
COPY . .

ENV AV_CONFIG=/app/config.yaml

# Web GUI (default)
EXPOSE 5000
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "--timeout", "0", "web.app:app"]
