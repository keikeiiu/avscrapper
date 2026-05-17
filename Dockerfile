FROM python:3.12-slim

# Install everything in one layer, then clean aggressively
RUN pip install --no-cache-dir pyyaml playwright flask gunicorn markdown \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache/pip \
    # Strip Chromium to essentials (keep en-US + ja for safety)
    && CHROMIUM=$(find /root/.cache/ms-playwright -name chrome-linux64 -type d | head -1) \
    && if [ -n "$CHROMIUM" ]; then \
         find "$CHROMIUM"/locales -name '*.pak' ! -name 'en-US.pak' ! -name 'ja.pak' -delete 2>/dev/null; \
         rm -rf "$CHROMIUM"/swiftshader 2>/dev/null; \
         rm -rf "$CHROMIUM"/MEIPreload 2>/dev/null; \
       fi

WORKDIR /app
COPY . .

ENV AV_CONFIG=/app/config.yaml

EXPOSE 5000
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "--timeout", "0", "web.app:app"]
