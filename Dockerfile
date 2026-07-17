# 美股投資分析報告產生器 — 容器化部署（Render / Railway / Fly.io / Zeabur / VPS 皆適用）
FROM python:3.12-slim

# WeasyPrint 原生庫 + 中文字型（CJK）+ 建置工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi-dev \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 多數 PaaS 會以 $PORT 指定埠；本地預設 8501
ENV PORT=8501
EXPOSE 8501

# 以 shell 形式展開 $PORT
CMD streamlit run app.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
