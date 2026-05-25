FROM python:3.13-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip build && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .


FROM python:3.13-slim

RUN useradd --system --uid 65532 --no-create-home --shell /usr/sbin/nologin sirius

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

USER 65532
EXPOSE 8080
ENTRYPOINT ["python", "-m", "sirius_operator"]
