.PHONY: install lint format test up down logs load k8s-up k8s-down

install:
	pip install -r requirements-dev.txt

lint:
	ruff check . && ruff format --check .

format:
	ruff check --fix . && ruff format .

test:
	pytest --cov=app --cov-report=term-missing

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f web

# Generate traffic so the Grafana dashboard has data
load:
	for i in $$(seq 1 300); do curl -s localhost:5000/ > /dev/null; curl -s localhost:5000/todos > /dev/null; done; echo done

# Local Kubernetes with kind
k8s-up:
	docker build -t docker-flask-demo:local .
	kind create cluster --name demo || true
	kind load docker-image docker-flask-demo:local --name demo
	kubectl apply -k k8s/

k8s-down:
	kind delete cluster --name demo
