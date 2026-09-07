#!/bin/sh
set -e

# main.py / database.py 使用相对路径（./app.db、secret.key），
# 直接对 /app 挂卷会覆盖代码，因此把这两个可变文件软链到 /data，
# 只需挂载 /data 即可持久化数据库与 JWT 密钥。
mkdir -p /data
ln -sfn /data/app.db      /app/app.db
ln -sfn /data/secret.key  /app/secret.key

exec "$@"
