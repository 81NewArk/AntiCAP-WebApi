FROM python:3.10.6-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# 先克隆仓库到临时目录，然后复制文件
RUN git clone https://github.com/81NewArk/AntiCAP-WebApi /tmp/source \
    && cp -r /tmp/source/* . \
    && cp -r /tmp/source/.* . 2>/dev/null || true \
    && rm -rf /tmp/source

# 或者直接检查文件是否存在
RUN if [ ! -f "main.py" ]; then \
        echo "错误：main.py 文件不存在，当前目录内容：" && ls -la; \
        exit 1; \
    fi

# 创建静态文件目录
RUN mkdir -p static

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 创建启动脚本
RUN cat > /entrypoint.sh << 'EOF'
#!/bin/bash
set -e

cd /app

echo "当前工作目录: $(pwd)"
echo "目录内容:"
ls -la

# 如果环境变量存在，则生成新的 .env 文件
if [ -n "$USERNAME" ] || [ -n "$PASSWORD" ] || [ -n "$PORT" ]; then
    echo "使用环境变量生成新配置"
    cat > .env << EOL
USERNAME=${USERNAME:-admin}
PASSWORD=${PASSWORD:-admin123}
PORT=${PORT:-6688}
EOL
elif [ ! -f .env ]; then
    echo "使用默认配置"
    cat > .env << EOL
USERNAME=admin
PASSWORD=admin123
PORT=6688
EOL
else
    echo "使用现有的 .env 文件"
fi

echo "启动 AntiCAP WebApi 服务..."
exec python main.py
EOF

RUN chmod +x /entrypoint.sh

EXPOSE 6688

ENTRYPOINT ["/entrypoint.sh"]
