FROM docker.io/python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget nginx tar && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /data/temp /data/out

COPY worker.py /usr/local/bin/diode-worker
COPY nginx.conf /etc/nginx/nginx.conf
RUN chmod +x /usr/local/bin/diode-worker

EXPOSE 8080
CMD ["/bin/sh", "-c", "diode-worker & nginx -g 'daemon off;'"]
