FROM python:3.9-slim

WORKDIR /app

# 安装git并克隆仓库
RUN apt-get update && apt-get install -y git && \
    git clone https://github.com/81NewArk/AntiCAP-WebApi . && \
    rm -rf /var/lib/apt/lists/*

# 创建入口脚本
RUN echo '#!/bin/bash\n\
if [ ! -f .env ]; then\n\
  echo "USERNAME=${USERNAME:-admin}" > .env\n\
  echo "PASSWORD=${PASSWORD:-defaultpass123}" >> .env\n\
  echo "PORT=${PORT:-6688}" >> .env\n\
fi\n\
exec python main.py' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

EXPOSE 6688

ENTRYPOINT ["/entrypoint.sh"]
