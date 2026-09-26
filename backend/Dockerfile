# GrowthCrew 后端镜像：非 root 运行，镜像内不含任何密钥
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# 生产镜像必须含 agents（langgraph/fastmcp/openai）和 jobs（apscheduler）依赖
RUN pip install --no-cache-dir ".[agents,jobs]"

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
