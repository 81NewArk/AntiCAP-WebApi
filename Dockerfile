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
    libgl1-mesa-glx

# 克隆仓库
RUN git clone https://github.com/81NewArk/AntiCAP-WebApi . 

# 创建静态文件目录
RUN mkdir -p static

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 创建启动脚本
RUN echo '#!/bin/bash\n\
# 如果环境变量存在，则生成新的 .env 文件\n\
if [ -n "$USERNAME" ] || [ -n "$PASSWORD" ] || [ -n "$PORT" ]; then\n\
    echo "USERNAME=${USERNAME:-admin}" > .env\n\
    echo "PASSWORD=${PASSWORD:-admin123}" >> .env\n\
    echo "PORT=${PORT:-6688}" >> .env\n\
    echo "使用环境变量生成新配置"\n\
elif [ ! -f .env ]; then\n\
    echo "USERNAME=admin" > .env\n\
    echo "PASSWORD=admin123" >> .env\n\
    echo "PORT=6688" >> .env\n\
    echo "使用默认配置"\n\
fi\n\
\n\
# 启动应用\n\
exec python main.py' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

EXPOSE 6688

ENTRYPOINT ["/entrypoint.sh"]
