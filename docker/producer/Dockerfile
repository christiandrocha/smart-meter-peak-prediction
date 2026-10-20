# Replay producer. Build from the repository root:
#   docker build -f docker/producer/Dockerfile -t smart-meter-producer .
#
# Run (credentials only through the git-ignored .env; sample and CA mounted read-only;
# the two -e flags override the host paths from .env with the container paths):
#   docker run --rm --user "$(id -u):$(id -g)" --env-file .env \
#     -e KAFKA_CA_PATH=/certs/ca.pem -e SAMPLE_STREAM_FILE=/data/readings_stream.csv \
#     -v "$PWD/data/sample/seed42/stream/readings_stream.csv:/data/readings_stream.csv:ro" \
#     -v /absolute/path/outside/repo/ca.pem:/certs/ca.pem:ro \
#     smart-meter-producer
# Notes: --user lets the container read a 0600 CA file owned by you; --env-file keeps quotes
# around values literally, so write KEY=value without quotes in .env.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[producer]" \
    && useradd --system --no-create-home producer

USER producer
ENTRYPOINT ["python", "-m", "smart_meter_peak_prediction.producer"]
