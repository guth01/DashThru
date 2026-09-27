---
title: DashThru API
colorFrom: orange
colorTo: red
sdk: docker
app_port: 7860
models:
  - guth001/distilbert-drivethru-intent
short_description: FastAPI voice ordering backend
---

# DashThru

DashThru is a voice-enabled drive-thru ordering assistant. The React/Vite frontend accepts spoken or typed requests, while the FastAPI backend uses a fine-tuned DistilBERT intent classifier to understand orders and maintain a lightweight session cart.

## Features

- Voice input through the browser Web Speech API (Chrome and Edge)
- Typed ordering mode
- Menu browsing with one-click item requests
- Intent detection for greetings, menu questions, new orders, toppings, cancellations, checkout, and confirmation
- Basic entity extraction for quantities, sizes, menu items, and toppings
- Session-based cart state held by the backend

## Requirements

- Node.js and npm
- Python 3.11 or later
- A browser with Web Speech API support for voice ordering

## Getting started

### 1. Start the backend

From the project root:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 7860
```

On startup, the backend downloads `guth001/distilbert-drivethru-intent` from Hugging Face and caches it under `/tmp/dashthru-model` by default. The first startup may take a while.

### 2. Start the frontend

In a second terminal, from the project root:

```bash
npm install
npm run dev
```

Open the Vite URL shown in the terminal, usually `http://localhost:5173`.

## Configuration

The frontend uses `http://localhost:7860` unless `VITE_API_URL` is set at build time:

```bash
VITE_API_URL=https://api.example.com npm run build
```

The backend supports these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODEL_REPO` | `guth001/distilbert-drivethru-intent` | Hugging Face model repository |
| `MODEL_CACHE` | `/tmp/dashthru-model` | Model cache directory |
| `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` | unset | Optional Hugging Face token for private or gated models |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed frontend origins |

For a deployed frontend, set `CORS_ORIGINS` to its exact origin, for example `https://app.example.com`.

## API

### `GET /`

Health check:

```json
{"service":"DashThru voice ordering API","status":"ok"}
```

### `POST /predict`

Request:

```json
{
  "text": "I want two large pepperoni pizzas with extra cheese",
  "session_id": "a-client-generated-session-id"
}
```

Response fields include the assistant reply, detected intent, model confidence, and the current cart:

```json
{
  "reply": "Got it - 2 large pepperoni pizzas with extra cheese added to your order.",
  "intent": "order_item",
  "confidence": 0.98,
  "cart": [
    {
      "item": "pepperoni",
      "quantity": 2,
      "size": "large",
      "toppings": ["extra cheese"]
    }
  ]
}
```

## Docker

Build and run the backend container:

```bash
cd backend
docker build -t dashthru-api .
docker run --rm -p 7860:7860 -e CORS_ORIGINS=http://localhost:5173 dashthru-api
```

The frontend is still run separately with Vite unless you add a static hosting layer for the built assets.

## Project structure

```text
src/                 React frontend and styles
backend/app.py       FastAPI API, model inference, entity extraction, and cart logic
backend/requirements.txt
backend/Dockerfile
index.html
package.json
```

## Development notes

Cart state is stored in backend memory and is keyed by the frontend-generated session ID. It resets when the backend restarts and is not suitable for production persistence or multiple backend workers without a shared datastore.

The intent model is a classifier rather than a general-purpose conversational model. Short, specific requests with correctly spelled menu items produce the most reliable results.

## License

No license has been specified for this project yet.
