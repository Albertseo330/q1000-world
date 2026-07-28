FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ARG KATAGO_VERSION=1.16.5
ARG KATAGO_SHA256=6e193040d90400eac828ebbfc49697b226eaaab69d0bfefba77a16126cb4ed25
ARG MODEL_URL=https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b18c384nbt-s9372115968-d4150170048.bin.gz

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KATAGO_PATH=/opt/katago/katago \
    KATAGO_MODEL=/opt/katago/model.bin.gz \
    KATAGO_CONFIG=/opt/katago/analysis.cfg

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip libgomp1 python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/katago \
    && curl -fL "https://github.com/lightvector/KataGo/releases/download/v${KATAGO_VERSION}/katago-v${KATAGO_VERSION}-cuda12.1-cudnn8.9.7-linux-x64.zip" -o /tmp/katago.zip \
    && echo "${KATAGO_SHA256}  /tmp/katago.zip" | sha256sum -c - \
    && unzip /tmp/katago.zip -d /opt/katago \
    && chmod +x /opt/katago/katago \
    && curl -fL "${MODEL_URL}" -o /opt/katago/model.bin.gz \
    && rm /tmp/katago.zip \
    && pip3 install --no-cache-dir runpod==1.7.13

COPY analysis.cfg /opt/katago/analysis.cfg
COPY katago-worker/rp_handler.py /opt/q1000/rp_handler.py

WORKDIR /opt/q1000
CMD ["python3", "-u", "rp_handler.py"]
