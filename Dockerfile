FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the omium-mcp package (sources + console script).
COPY pyproject.toml README.md ./
COPY omium_mcp ./omium_mcp
RUN pip install .

EXPOSE 9100

# HTTP transport — BearerAuthMiddleware extracts the API key per request.
CMD ["omium-mcp", "serve"]
