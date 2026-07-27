# TerraSignal backend image — FastAPI + the ML pipeline that seeds it.
#
# The frontend is deployed separately (Vercel); this image serves the API only.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
# PYTHONHASHSEED is pinned deliberately: the synthetic generator's rng draw
# count varies with hash iteration order, so an unpinned seed produces a
# different portfolio on every container start — and the trainer's metric gates
# move with it. Pinning makes the "one seed -> one deterministic portfolio"
# guarantee in the README actually hold.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first, so the layer caches until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Project sources.
COPY shared ./shared
COPY terrasignal ./terrasignal
RUN uv sync --frozen --no-dev

COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
