FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple uv==0.13.9 \
    && uv pip install --system --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt \
    "torch @ https://mirrors.aliyun.com/pytorch-wheels/cpu/torch-2.15.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl#sha256=0955c7e3446326293f48af18fad67872fa31dee5a36a87690eb9e5be8b465be3" \
    && pip uninstall -y uv

COPY app ./app
COPY data/kb ./data/kb

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]