FROM python:3.10.6-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p static

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 创建启动脚本
RUN cat > /app/start.sh << 'EOF'
#!/bin/bash
cd /app

echo "=== AntiCAP WebApi 启动 ==="
echo "工作目录: $(pwd)"
echo "项目文件:"
ls -la

# 配置处理
if [ -n "$USERNAME" ] || [ -n "$PASSWORD" ] || [ -n "$PORT" ]; then
    echo "使用环境变量生成配置"
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
    echo "使用现有配置文件"
fi

echo "配置文件内容:"
cat .env

echo "=== 启动服务 ==="
exec python main.py
EOF

RUN chmod +x /app/start.sh

EXPOSE 6688

CMD ["/app/start.sh"]
