# syntax=docker/dockerfile:1
#
# One image, one URL: FastAPI serves both the API and the built React frontend.
# Build from the repository root:   docker build -t cardiac-function-ai .
# Run:                              docker run -p 7860:7860 cardiac-function-ai

# ---------- stage 1: build the frontend ----------
FROM node:22-slim AS frontend
WORKDIR /build
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY app/frontend/ ./
RUN npm run build

# ---------- stage 2: Python runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# CPU-only PyTorch keeps the image ~1.5 GB smaller than the default CUDA wheels.
# Installed first so that the requirements file finds torch already satisfied.
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# A non-root user is required by Hugging Face Spaces and is good practice anywhere.
RUN useradd --create-home --uid 1000 appuser
WORKDIR /home/appuser/app

COPY --chown=appuser app/backend ./app/backend
COPY --chown=appuser segmentation/segmentation_module.py ./segmentation/segmentation_module.py
COPY --chown=appuser ef_engine/ef_module.py ./ef_engine/ef_module.py
# Trained weights + metadata. The .pth file is not in git (too large); see
# DEPLOYMENT.md for the two supported ways to provide it (MODEL_URL or a copy here).
COPY --chown=appuser segmentation/checkpoints ./segmentation/checkpoints
COPY --from=frontend --chown=appuser /build/dist ./app/frontend/dist

USER appuser

ENV SEG_CKPT=/home/appuser/app/segmentation/checkpoints/deeplabv3_lv_segmentation.pth \
    FRONTEND_DIR=/home/appuser/app/app/frontend/dist \
    OVERLAY_DIR=/tmp/cardiac_overlays

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)" || exit 1

WORKDIR /home/appuser/app/app/backend
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
