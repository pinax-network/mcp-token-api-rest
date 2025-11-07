# Use Python 3.11 slim image
FROM python:3.11-slim as builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies
RUN uv pip install --system --no-cache-dir .

# Runtime stage
FROM python:3.11-slim

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy application code
COPY src/ ./src/

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080
# Token API connection (override these at runtime)
ENV TOKEN_API_BASE_URL=https://token-api.thegraph.com
ENV OPENAPI_SPEC_URL=${TOKEN_API_BASE_URL}/openapi
# Hot-reload configuration (5 minutes default)
ENV VERSION_CHECK_INTERVAL=300

# Health check - removed since MCP doesn't have /health endpoint
# Instead check if the process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "python.*server.py" > /dev/null || exit 1

EXPOSE 8080

# Run the server
CMD ["python", "-m", "src.server"]