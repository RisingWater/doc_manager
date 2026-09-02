FROM ubuntu:24.04

ARG UID=1002
ENV UID=${UID}
ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/ubuntu.sources && \
    sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/ubuntu.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    python3 python3-pip python3-venv \
    build-essential \
    locales \
    && rm -rf /var/lib/apt/lists/*

# 中文 locale（文件名含中文，必须 UTF-8）
RUN locale-gen zh_CN.UTF-8 && update-locale LANG=zh_CN.UTF-8
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN:zh
ENV LC_ALL=zh_CN.UTF-8

# Bun（用于构建前端）
RUN curl -fsSL https://bun.sh/install | BUN_INSTALL="/usr/local" bash
ENV PATH="/usr/local/bin:${PATH}"

# 非 root 用户（上传文件、数据库落盘都用该 UID，避免 root 权限问题）
RUN useradd -m -u $UID appuser

WORKDIR /workdir

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

CMD ["bash", "deploy/run.sh"]
