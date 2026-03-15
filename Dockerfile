FROM python:3.13-slim AS builder

RUN pip install poetry==2.1.3

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# Install deps into a virtualenv inside the builder stage
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-root --only main

FROM python:3.13-slim

WORKDIR /app

# Copy the virtualenv from builder
COPY --from=builder /app/.venv .venv

# Copy application code
COPY app/ app/
COPY data/ data/
COPY mini_app/ mini_app/
COPY run_bot.py run_migrations.py embed_data.py report_bot.py ./

ENV PATH="/app/.venv/bin:$PATH"

# Default: run the Telegram bot
CMD ["python", "run_bot.py"]
