FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt

# torch's wheel on PyPI is the CUDA build, and it declares the CUDA runtime as
# hard requirements — cuDNN, cuBLAS, cuSOLVER, NCCL, triton and the rest, about
# 2.0 GB. pip installs them because torch's metadata says to, not because
# anything looked at the hardware. This container has no GPU and Railway does
# not sell one, so those libraries are never opened: pure image weight.
#
# PyTorch's own index serves the identical version built without them, 187 MB
# against 2.8 GB. Installed BEFORE requirements.txt so that pip finds the pin
# there already satisfied — 2.2.2+cpu matches ==2.2.2 under PEP 440, since a
# specifier with no local version ignores one. requirements.txt therefore stays
# unchanged and a local (macOS, already CPU-only) install is unaffected.
#
# --index-url, not --extra-index-url: the latter merely ADDS a source and lets
# pip pick the CUDA wheel anyway. This must be its own RUN, because the CPU
# index carries only torch-family packages and everything else would 404.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.2.2

RUN pip install --no-cache-dir -r backend/requirements.txt

# Keep backend/, frontend/, and data/ as siblings, same as the repo layout —
# app/main.py and app/rag/retriever.py both resolve paths relative to that.
COPY backend/ backend/
COPY frontend/ frontend/
COPY data/ data/

WORKDIR /app/backend

# Railway injects $PORT; fall back to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
