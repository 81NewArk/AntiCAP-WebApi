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
    libgl1-mesa-glx && \
    rm -rf /var/lib/apt/lists/*

# 克隆仓库
RUN git clone https://github.com/81NewArk/AntiCAP-WebApi . 

# 创建静态文件目录
RUN mkdir -p static

# 在构建时创建默认 .env 文件
RUN echo "USERNAME=admin" > .env && \
    echo "PASSWORD=admin" >> .env && \
    echo "PORT=6688" >> .env

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 设置默认环境变量（可选）
ENV USERNAME=admin
ENV PASSWORD=defaultpass123
ENV PORT=6688

EXPOSE 6688

CMD ["python", "main.py"]
