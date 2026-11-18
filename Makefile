.PHONY: up down logs config

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f streamlit-app evaluator-worker otel-collector

config:
	docker compose config --quiet
