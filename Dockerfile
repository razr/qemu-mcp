FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    qemu-system-x86 \
    qemu-system-arm \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Define version and clone the FULL repository path
RUN QEMU_VERSION=$(qemu-system-x86_64 --version | grep -oP 'version \K[0-9]+\.[0-9]+') \
    && echo "Installing python tools for QEMU $QEMU_VERSION" \
    && git clone --depth 1 --branch "stable-$QEMU_VERSION" https://gitlab.com/qemu-project/qemu.git /tmp/qemu \
    && cd /tmp/qemu/python \
    && pip install . \
    && rm -rf /tmp/qemu

COPY . .

RUN pip install --no-cache-dir \
    fastmcp \
    pyelftools \
    psutil \
    qemu.qmp

RUN pip install -e .

EXPOSE 15555
EXPOSE 1534
EXPOSE 2345

ENTRYPOINT ["qemu-mcp"]

