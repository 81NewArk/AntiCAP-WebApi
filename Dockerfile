# 使用官方 Python 3.9 精简版作为基础镜像
FROM python:3.9-slim

# 在容器中设置工作目录
WORKDIR /app

# 安装 git 并克隆仓库（如果使用本地文件构建，可以用 COPY 替代）
RUN apt-get update && apt-get install -y git && \
    git clone https://github.com/81NewArk/AntiCAP-WebApi . && \
    rm -rf /var/lib/apt/lists/*

# 使用清华源安装项目依赖（--no-cache-dir 避免缓存增大镜像体积）
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 暴露默认端口 6688
EXPOSE 6688

# 创建数据卷用于持久化 .env 文件（保存账号密码）
VOLUME /app/.env

# 容器启动时运行的命令（会自动提示输入账号密码）
CMD ["python", "main.py"]
