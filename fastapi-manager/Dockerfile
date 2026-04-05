FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including opencv dependencies for scenedetect)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    libgl1 \
    libglib2.0-0 \
    openssh-client \
    rsync \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install rclone (architecture-aware)
RUN ARCH=$(dpkg --print-architecture) \
    && curl -O https://downloads.rclone.org/rclone-current-linux-${ARCH}.zip \
    && unzip rclone-current-linux-${ARCH}.zip \
    && cp rclone-*-linux-${ARCH}/rclone /usr/local/bin/ \
    && rm -rf rclone-*-linux-${ARCH}* \
    && chmod +x /usr/local/bin/rclone

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY requirements.txt .
RUN uv venv /app/.venv && uv pip install --no-cache -r requirements.txt

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
