FROM python:3.12-slim

WORKDIR /app

# gcc: needed for packages that compile C extensions at install time
# libgomp1: OpenMP runtime required by scikit-learn (Isolation Forest)
# curl: used by the Docker healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached until requirements change)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source (build context is the project root)
COPY backend/ ./backend/

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
