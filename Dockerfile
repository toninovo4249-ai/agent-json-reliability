FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
ENV HOST=127.0.0.1 PORT=8770
EXPOSE 8770
LABEL org.opencontainers.image.title="Agent JSON Reliability"
LABEL org.opencontainers.image.version="0.1.0"
CMD ["python", "serve.py"]
