FROM python:3.13-alpine

WORKDIR /app

RUN apk add postgresql-dev gcc musl-dev

COPY pyproject.toml /app/
COPY .env /app/

RUN pip install uv && uv sync

COPY . /app/

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]