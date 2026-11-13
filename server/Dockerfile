FROM python:3.12-slim

# 时区与是否缓冲输出；不写 pip 镜像，构建机想加速请自己传 --build-arg
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖先装，利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 非 root 运行：应用只写 /data（SQLite）和 /apk（只读挂载）
# chmod 用于抹平构建上下文里带进来的异常权限位（源码经跨平台同步后可能丢掉可读位）
RUN useradd --create-home --uid 10001 miaoledger \
    && mkdir -p /data /apk \
    && chown -R miaoledger:miaoledger /app /data \
    && chmod -R a+rX /app/app
USER miaoledger

ENV DATABASE_URL=sqlite:////data/miaoledger.db \
    APK_DIR=/apk

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
