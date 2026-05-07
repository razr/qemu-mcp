FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    qemu-system-x86 \
    qemu-system-arm \
    libvirt-dev \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Определяем версию установленного QEMU и скачиваем соответствующий код
RUN QEMU_VERSION=$(qemu-system-x86_64 --version | grep -oP 'version \K[0-9]+\.[0-9]+') \
    && echo "Matching QEMU version: $QEMU_VERSION" \
    && git clone --depth 1 --branch v$QEMU_VERSION.0 https://gitlab.com /tmp/qemu \
    || git clone --depth 1 --branch v$QEMU_VERSION.7 https://gitlab.com /tmp/qemu \
    && pip install /tmp/qemu/python \
    && rm -rf /tmp/qemu

COPY . .

RUN pip install --no-cache-dir \
    fastmcp \
    pyelftools \
    psutil \
    qemu.qmp

RUN pip install -e .

ENTRYPOINT ["qemu-mcp"]

