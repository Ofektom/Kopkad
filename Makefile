# Run the FastAPI app locally with uv
run:
	uv run uvicorn main:app --reload

# Generate an Alembic migration
migrate:
	uv run alembic revision --autogenerate -m "$(MSG)"

# Apply migrations to the database
upgrade:
	uv run alembic upgrade head

# Roll back the last migration
downgrade:
	uv run alembic downgrade -1

# Build the Docker image
docker-build:
	docker build -t savings-system:latest .

# Run the Docker container locally
docker-run:
	docker run -p 8001:8001 -v ./logs:/app/logs savings-system:latest

# Run Docker Compose (builds and starts app + PostgreSQL)
compose:
	docker compose up --build

# Stop Docker Compose
compose-down:
	docker compose down

# Clean up (remove virtual environment, pycache, etc.)
clean:
	rm -rf .venv __pycache__ *.pyc