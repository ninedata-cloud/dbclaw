# SmartDBA - AI-powered Database Operations Platform
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    freetds-dev \
    freetds-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download sentence-transformers embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY run.py .

# Create data directories (will be overridden by volumes)
RUN mkdir -p data/chroma uploads/chat_attachments data/knowledge_bases

# Expose the application port
EXPOSE 8000

# Non-root user for security
RUN useradd -m -u 1000 smartdba && chown -R smartdba:smartdba /app
USER smartdba

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "run.py"]
