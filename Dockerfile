# 基础镜像：选择轻量的Python 3.10 slim版本（减小镜像体积）
FROM python:3.10-slim

# 设置工作目录（容器内的代码目录）
WORKDIR /app

# 安装系统依赖（解决pymysql等模块的编译问题，可选但建议加）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单文件到容器
COPY requirements.txt .

# 安装Python依赖（--no-cache-dir 避免缓存，减小镜像体积）
RUN pip install --no-cache-dir -r requirements.txt

# 复制本地所有代码到容器的/app目录
COPY . .

# 设置环境变量：确保Python输出实时打印（方便查看日志）
ENV PYTHONUNBUFFERED=1

# 启动命令：运行机器人主程序（根据你的主文件名称调整，比如bot.py/local_bot.py）
CMD ["python", "bot.py"]