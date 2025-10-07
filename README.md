# Financial Forecasting Application

A full-stack scaffold for a financial forecasting application with Flask, React, and ML placeholders. Includes Docker support and basic tests.

## Project Structure

```
backend/           # Flask API
frontend/          # React + Vite app
ML_models/         # ML code scaffolding
database/          # DB schemas
tests/             # Unit tests
requirements.txt   # Python dependencies
.gitignore         # Python & Node ignores
backend/Dockerfile # Backend image build
frontend/Dockerfile# Frontend image build
docker-compose.yml # Orchestrates services
```

## Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (optional, for containerized setup)

## Backend (Flask)

Install dependencies and run:

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend/app.py
```

API endpoints:
- GET /health – health check
- POST /api/forecast – body: { "ticker": "AAPL", "horizon": 7 }

## Frontend (React + Vite)

```bash
cd frontend
npm install
npm run start
```
The dev server proxies /api to http://localhost:5000.

## Tests

```bash
pytest -q
```

## Docker

Build and run all services:

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:5000
- MongoDB: localhost:27017
- Redis: localhost:6379

## Notes
- requirements.txt includes heavy ML frameworks (TensorFlow, PyTorch, Keras, TA-Lib). Building may take time and some packages require system dependencies (e.g., TA-Lib). If not needed immediately, remove or pin lighter versions.
- database/schema.sql is a generic SQL schema example; adjust for your chosen DB.
