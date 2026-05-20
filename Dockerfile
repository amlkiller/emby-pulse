FROM python:3.9-slim AS builder
WORKDIR /build
COPY app/ ./app/
RUN python -m compileall -b app/
RUN find app/ -name "*.py" -delete

FROM python:3.9-slim
WORKDIR /workspace
# 修改这里自定义版本号
ENV APP_VERSION=1.4.4
ENV TZ=Asia/Shanghai

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY --from=builder /build/app ./app
COPY run.py ./run.py
COPY templates ./templates
COPY static ./static

# 预创建数据目录（volume 挂载点）
# 以 root 运行，避免宿主机挂载目录属主不匹配导致的写入权限问题
RUN mkdir -p /workspace/config /workspace/data

EXPOSE 10307 10308
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10307"]