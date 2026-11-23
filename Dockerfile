FROM python:3.10-slim

# Install system dependencies (ffmpeg for audio/video conversion and muxing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs as user with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860 \
    IS_CLOUD=true

WORKDIR $HOME/app

# Install Python dependencies
COPY --chown=user requirements.txt $HOME/app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r $HOME/app/requirements.txt

# Copy application source
COPY --chown=user . $HOME/app

# Ensure downloads directory exists
RUN mkdir -p $HOME/app/downloads

# Expose Space port
EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
