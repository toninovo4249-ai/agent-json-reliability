# syntax=docker/dockerfile:1
# Optional cloud HTTP image. Local MCP stdio (`uvx agent-json-reliability`) does not use this.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV HOST=0.0.0.0
ENV PUBLIC_BETA_CONFIRM=true
ENV X402_PAYMENT_ENABLED=false
ENV PAID_ROUTE_ENABLED=false
ENV MAINNET_PAYMENT_ENABLED=false
EXPOSE 8770
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8770')+'/health')"
CMD ["python", "serve.py"]
