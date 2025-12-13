FROM python:3.11-slim

# System deps: Java + unzip + wget
RUN apt-get update && apt-get install -y \
    openjdk-17-jre-headless \
    unzip \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install JADX
RUN mkdir -p /opt/jadx \
    && wget -O /tmp/jadx.zip https://github.com/skylot/jadx/releases/download/v1.5.0/jadx-1.5.0.zip \
    && unzip /tmp/jadx.zip -d /opt/jadx \
    && rm /tmp/jadx.zip

# Used by main.py
ENV JADDX_CLI_JAR=/opt/jadx/jadx-1.5.0/bin/jadx-cli.jar

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . /app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
