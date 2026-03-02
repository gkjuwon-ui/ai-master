# ═══════════════════════════════════════════════════════════════
#  Ogenti — RunPod Serverless Worker Dockerfile
#
#  Build & push:
#    docker build -t <your-dockerhub>/ogenti-worker:latest ./runpod_worker
#    docker push <your-dockerhub>/ogenti-worker:latest
#
#  Then create a RunPod Serverless Endpoint with this image.
# ═══════════════════════════════════════════════════════════════

FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    runpod>=1.6.0 \
    transformers>=4.40.0 \
    peft>=0.10.0 \
    trl>=0.8.0 \
    accelerate>=0.28.0 \
    datasets>=2.18.0 \
    sentencepiece>=0.1.99 \
    safetensors>=0.4.0 \
    bitsandbytes>=0.43.0 \
    httpx>=0.27.0 \
    scipy>=1.12.0

# Copy handler
COPY handler.py /app/handler.py

# Pre-download small model (optional, speeds up cold start)
# RUN python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('Qwen/Qwen2.5-3B-Instruct', trust_remote_code=True)"

ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "/app/handler.py"]
