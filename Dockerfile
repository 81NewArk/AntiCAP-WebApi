# syntax=docker/dockerfile:1

# ============================================================
# builder：安装依赖到独立 venv，便于整体拷贝到运行阶段
# ============================================================
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# bcrypt / scipy 等极端情况下需要编译，仅在 builder 阶段安装编译链
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 1) 先钉住 numpy，避免后续被 torchvision 拉到 2.x 再降级导致 ABI 告警
RUN pip install numpy==1.26.4

# 2) 关键优化：显式安装 CPU 版 torch/torchvision，避免 ultralytics 拉入 CUDA 版
#    - amd64：必须走 PyTorch 的 cpu 专用索引，否则会带上 nvidia-* 全套 wheel（+4GB）
#    - arm64：PyPI 上的 aarch64 wheel 本身就是纯 CPU 版（nvidia/triton 依赖被
#      `platform_machine == "x86_64"` 标记排除），直接用 PyPI 即可
ARG TARGETARCH
RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    if [ "$arch" = "arm64" ]; then \
      pip install torch==2.4.1 torchvision==0.19.1; \
    else \
      pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.4.1 torchvision==0.19.1; \
    fi; \
    ! pip list 2>/dev/null | grep -qi '^nvidia-'

# 3) 业务依赖
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 4) opencv-python 是 AntiCAP/ultralytics 的传递依赖（GUI 版，需 libGL 等系统库）。
#    服务端用不到 GUI，替换为 headless 版：体积更小、运行时系统依赖更少
RUN pip uninstall -y opencv-python opencv-python-headless || true \
 && pip install opencv-python-headless==4.10.0.84

# 5) 构建期预下载 AntiCAP 模型（约数百 MB）。
#    模型不在 wheel 内，默认是首次启动时从 https://newark81.vip/AntiCAP-Models/ 下载，
#    下载失败会抛 IOError 导致容器起不来。预下载可让启动不依赖外网。
#    源站不可达时这里只告警不中断构建，模型会退回到运行时下载。
ARG PREDOWNLOAD_MODELS=true
RUN if [ "$PREDOWNLOAD_MODELS" = "true" ]; then \
      python -c "import AntiCAP; AntiCAP.Handler(show_banner=False)" \
      || echo ">>> WARNING: 模型预下载失败，将在容器首次启动时重试下载（需要外网）"; \
    fi

# ============================================================
# runtime：只带运行期需要的东西
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    MPLCONFIGDIR=/tmp/matplotlib \
    YOLO_CONFIG_DIR=/tmp

# libgomp1: torch / onnxruntime / scipy 的 OpenMP 运行时
# libglib2.0-0: opencv headless 仍依赖
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY main.py database.py ./
COPY static ./static
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# /data 存放 app.db 与 secret.key（entrypoint 会做软链）
# AntiCAP-Models 目录需可写，以便预下载失败时运行期补下载
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && mkdir -p /data /opt/venv/lib/python3.11/site-packages/AntiCAP/AntiCAP-Models \
 && chown -R appuser:appuser /app /data /opt/venv/lib/python3.11/site-packages/AntiCAP

USER appuser

EXPOSE 6688
VOLUME ["/data"]

# 探测 /healthz 而不是 /docs：不渲染 Swagger 页面，且其访问日志被应用过滤掉。
# interval 放宽到 60s——每次探测都要起一个 python 解释器，SBC 上不必太频繁。
# start-period 留 180s：首次启动若需下载模型，加载会比较久。
HEALTHCHECK --interval=60s --timeout=5s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:6688/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "main.py"]
