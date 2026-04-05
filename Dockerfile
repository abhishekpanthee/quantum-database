FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/abhishekpanthee/quantum-database"
LABEL org.opencontainers.image.description="QNDB — Quantum-Native Database Engine"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY setup.py pyproject.toml MANIFEST.in README.md LICENSE ./
COPY qndb/ ./qndb/
COPY examples/ ./examples/
COPY benchmarks.py ./

RUN pip install --no-cache-dir .

CMD ["python", "-c", "import qndb; print(f'qndb {qndb.__version__} ready')"]
