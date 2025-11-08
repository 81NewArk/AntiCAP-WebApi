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
    && apt-get clean

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p static

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 使用 printf 创建脚本，避免换行符问题
RUN printf '#!/bin/bash\n\
cd /app\n\
\n\
echo "=== AntiCAP WebApi 启动 === "\n\
echo "工作目录: $(pwd)"\n\
echo "项目文件:"\n\
ls -la\n\
\n\
# 配置处理\n\
if [ -n "$USERNAME" ] || [ -n "$PASSWORD" ] || [ -n "$PORT" ]; then\n\
    echo "使用环境变量生成配置"\n\
    cat > .env << EOL\n\
USERNAME=${USERNAME:-admin}\n\
PASSWORD=${PASSWORD:-admin123}\n\
PORT=${PORT:-6688}\n\
EOL\n\
elif [ ! -f .env ]; then\n\
    echo "使用默认配置"\n\
    cat > .env << EOL\n\
USERNAME=admin\n\
PASSWORD=admin123\n\
PORT=6688\n\
EOL\n\
else\n\
    echo "使用现有配置文件"\n\
fi\n\
\n\
echo "配置文件内容:"\n\
cat .env\n\
\n\
echo "=== 启动服务 === "\n\
exec python main.py\n' > /app/start.sh

RUN chmod +x /app/start.sh

# 安装 dos2unix 并转换换行符
RUN apt-get update && apt-get install -y dos2unix && dos2unix /app/start.sh

EXPOSE 6688

CMD ["/app/start.sh"]
