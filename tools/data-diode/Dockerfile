FROM docker.io/python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget nginx tar coreutils && rm -rf /var/lib/apt/lists/*

COPY worker.py /usr/local/bin/diode-worker
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 8080
CMD ["sh", "-c", "rm -rf /data/temp && find /data/out -mtime +7 -delete && nginx -g 'daemon off;' & diode-worker"]
