# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /build
COPY app/ ./app/
RUN python -m compileall -b app/
RUN find app/ -name "*.py" -delete

FROM python:3.12-slim
WORKDIR /workspace
# 修改这里自定义版本号
ENV APP_VERSION=1.5.0-beta
ENV TZ=Asia/Shanghai
ENV PATH="/workspace/.venv/bin:$PATH"
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# 先按锁文件安装依赖，利用 Docker 层缓存
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --locked --no-dev --no-install-project
RUN /workspace/.venv/bin/python -m uvicorn --version

COPY --from=builder /build/app ./app
COPY run.py ./run.py
COPY templates ./templates
COPY static ./static

# 预创建数据目录（volume 挂载点）
# 以 root 运行，避免宿主机挂载目录属主不匹配导致的写入权限问题
RUN mkdir -p /workspace/config /workspace/data

EXPOSE 10307 10308
CMD ["/workspace/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10307"]
