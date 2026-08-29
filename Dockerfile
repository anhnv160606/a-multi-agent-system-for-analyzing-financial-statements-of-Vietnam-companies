# Multi-Agent Financial Analysis System - All-in-One Dockerfile
FROM python:3.11-slim

# Prevent Python from writing .pyc files & unbuffered stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=3000

WORKDIR /app

# 1. Install system dependencies & Node.js 20
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy and install pure Python dependencies
COPY requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

# 3. Copy frontend and backend package configs first for caching
COPY frontend/package*.json ./frontend/
COPY backend/package*.json ./backend/
COPY package*.json ./

# 4. Install Node dependencies
RUN cd backend && npm install --omit=dev
RUN cd frontend && npm install

# 5. Copy all project files
COPY . .

# 6. Build production React frontend
RUN cd frontend && npm run build

# 7. Expose port 3000 for full Web UI & API
EXPOSE 3000
EXPOSE 5000

# 8. Start server
CMD ["node", "backend/server.js"]
