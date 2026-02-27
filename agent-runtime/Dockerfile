# ?�?�?� ogenti Agent Runtime ?�?�?� Dockerfile ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
# Python-based OS automation runtime with display support

FROM python:3.11-slim AS base

# Install system dependencies for pyautogui, mss, and display
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libx11-dev \
    libxext-dev \
    libxss-dev \
    libxi-dev \
    libxtst-dev \
    xdg-utils \
    scrot \
    xdotool \
    xclip \
    xvfb \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY agent-runtime/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent-runtime/ ./

# Create data directory
RUN mkdir -p /app/data /app/plugins

# Create non-root user
RUN groupadd -r ogenti && useradd -r -g ogenti ogenti
RUN chown -R ogenti:ogenti /app

USER ogenti

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &>/dev/null & exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
