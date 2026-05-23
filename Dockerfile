FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    qemu-system-x86 \
    qemu-system-arm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir \
    fastmcp \
    pyelftools \
    psutil

RUN pip install -e .

EXPOSE 15555
EXPOSE 15556
EXPOSE 1534
EXPOSE 2345

ENTRYPOINT ["qemu-mcp"]

