# Multi-Agent Financial Analysis System - Main App Dockerfile
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies (OCR, PDF processing, graphics, MySQL client)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    tesseract-ocr \
    tesseract-ocr-vie \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications first to leverage Docker layer caching
COPY pyproject.toml requirements.txt* ./

# Install Python packages if requirements.txt exists and is not empty
RUN if [ -s requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Copy source code and configurations
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Default command
CMD ["bash"]
