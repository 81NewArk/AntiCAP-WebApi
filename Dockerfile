FROM python:3.10.6-slim

WORKDIR /app

# 安装git并克隆仓库
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx && \ 
    git clone https://github.com/81NewArk/AntiCAP-WebApi .     

# 创建静态文件目录（如果不存在）
RUN mkdir -p static

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 创建入口脚本
RUN echo '#!/bin/bash\n\
if [ ! -f .env ] || [ -n "$USERNAME" ] || [ -n "$PASSWORD" ] || [ -n "$PORT" ]; then\n\
  echo "USERNAME=${USERNAME:-admin}" > .env\n\
  echo "PASSWORD=${PASSWORD:-defaultpass123}" >> .env\n\
  echo "PORT=${PORT:-6688}" >> .env\n\
fi\n\
exec python main.py' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

EXPOSE 6688

ENTRYPOINT ["/entrypoint.sh"]



