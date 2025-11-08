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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 克隆仓库并检查
RUN git clone https://github.com/81NewArk/AntiCAP-WebApi . \
    && echo "仓库内容：" && ls -la

# 创建静态文件目录
RUN mkdir -p static

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 创建启动脚本在当前目录
RUN cat > /app/start.sh << 'EOF'
#!/bin/bash
cd /app

echo "=== 环境检查 ==="
echo "工作目录: $(pwd)"
echo "文件列表:"
ls -la

# 配置处理
if [ -n "$USERNAME" ] || [ -n "$PASSWORD" ] || [ -n "$PORT" ]; then
    echo "生成环境变量配置"
    echo "USERNAME=${USERNAME:-admin}" > .env
    echo "PASSWORD=${PASSWORD:-admin123}" >> .env
    echo "PORT=${PORT:-6688}" >> .env
elif [ ! -f .env ]; then
    echo "生成默认配置"
    echo "USERNAME=admin" > .env
    echo "PASSWORD=admin123" >> .env
    echo "PORT=6688" >> .env
fi

echo "=== 启动应用 ==="
exec python main.py
EOF

RUN chmod +x /app/start.sh

EXPOSE 6688

# 使用绝对路径
CMD ["/app/start.sh"]
