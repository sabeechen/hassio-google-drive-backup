# The Home Assistant builder used to inject BUILD_FROM, but since Supervisor 2026.04 apps are
# expected to declare their base image explicitly.  base-python images are multi-arch
# (amd64 + arm64) and pin both the Alpine and Python versions.
FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

RUN apk add --no-cache fping

WORKDIR /app

# Install locked dependencies first so source changes don't invalidate the layer.
COPY pyproject.toml uv.lock .python-version /app/
ENV UV_PYTHON_DOWNLOADS=never
RUN uv sync --locked --no-dev --no-install-project --compile-bytecode

# The app runs from source in /app; settings.py expects config.json next to the backup package.
COPY . /app
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 1627
EXPOSE 8099
ENTRYPOINT ["python3", "-m", "backup"]
