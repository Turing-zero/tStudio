.PHONY: dev prod install clean build-frontend

# --- Development ---
dev:
	@echo "Starting development servers..."
	@make -j2 "dev-frontend" "dev-backend"

dev-frontend:
	@echo "Starting frontend (Dev Mode)..."
	@cd frontend && npm start

dev-backend:
	@echo "Starting backend (Dev Mode)..."
	@cd backend && python main.py

# --- Production ---
prod: build-frontend
	@echo "Starting backend (Production Mode)..."
	@echo "Note: In true production, serve frontend 'build' folder via Nginx"
	@make prod-backend

build-frontend:
	@echo "Building frontend static assets..."
	@cd frontend && npm run build

prod-backend:
	@echo "Starting backend (Production Mode)..."
	@cd backend && set ENV=PROD && python -m uvicorn main:app --host 0.0.0.0 --port 3500 --workers 4

install:
	@echo "Installing dependencies..."
	@cd frontend && npm install
	@cd backend && pip install -r requirements.txt

clean:
	@echo "Cleaning up..."
	@rm -rf node_modules
	@rm -rf .svelte-kit
	@find . -name "__pycache__" -exec rm -rf {} +
