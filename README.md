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

> A voice-first drive-thru ordering assistant for quick, natural food orders.

DashThru combines a React/Vite interface with a FastAPI backend and a fine-tuned DistilBERT intent classifier. Customers can speak or type an order, browse the menu, customize items, remove items, and check out through one conversation.

## At a glance

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | React + Vite | Voice and text ordering interface |
| Backend | FastAPI + Uvicorn | Prediction API and cart logic |
| Model | Hugging Face Inference Providers | Remote intent classification |
| Deployment | Docker | Reproducible backend runtime |

## What it can understand

- Greetings and menu questions
- New orders with quantities and sizes
- Toppings and customizations
- Item removal and cancellation
- Checkout and confirmation
- Menu browsing through one-click prompts

## Architecture

```text
Browser
  |
  |  voice or typed request
  v
React/Vite frontend
  |
  |  POST /predict
  v
FastAPI backend
  |
  +--> DistilBERT intent classifier
  +--> Entity extraction
  `--> In-memory session cart
```

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
```

Activate the environment:

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

The backend sends classification requests to Hugging Face Inference Providers using `guth001/distilbert-drivethru-intent`. The model weights are not loaded into the Render container, keeping the API lightweight enough for small instances.

### Frontend

Open a second terminal from the project root:

```bash
npm ci
npm run dev
```

Then open the Vite URL, normally `http://localhost:5173`.

The frontend uses `http://localhost:7860` by default. To point it at another backend, set `VITE_API_URL` before building:

```bash
VITE_API_URL=https://your-api.example.com npm run build
```

## API

### `GET /`

Returns a basic health response:

```json
{
  "service": "DashThru voice ordering API",
  "status": "ok"
}
```

### `POST /predict`

Request:

```json
{
  "text": "I want two large pepperoni pizzas with extra cheese",
  "session_id": "client-session-id"
}
```

Response:

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

Interactive API documentation is available at `/docs` when the backend is running.

## Deployment

The repository includes Docker support for deploying the backend as a web service. The frontend can be deployed as a static Vite site.

### Recommended deployment

```text
Render Web Service  -> FastAPI backend
Render Static Site  -> React/Vite frontend
Hugging Face        -> Model hosting
```

For the backend, use the root `Dockerfile`, expose port `7860`, and set:

```text
MODEL_REPO=guth001/distilbert-drivethru-intent
HF_PROVIDER=hf-inference
HF_TOKEN=your_hugging_face_token
CORS_ORIGINS=https://your-frontend.example.com
```

For the frontend, build with:

```text
npm ci && npm run build
```

and set:

```text
VITE_API_URL=https://your-backend.example.com
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_URL` | `http://localhost:7860` | Frontend API base URL |
| `MODEL_REPO` | `guth001/distilbert-drivethru-intent` | Hugging Face model repository |
| `MODEL_CACHE` | `/tmp/dashthru-model` | Temporary cache for the optional label mapping |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins |
| `HF_PROVIDER` | `hf-inference` | Hugging Face inference provider |
| `HF_TOKEN` | required | Hugging Face token with Inference Providers permission |

## Project structure

```text
.
├── src/                  # React application and styles
├── backend/
│   ├── app.py            # FastAPI API and ordering logic
│   ├── requirements.txt  # Python dependencies
│   └── Dockerfile        # Backend-only container
├── Dockerfile            # Deployment container for the backend
├── index.html
├── package.json
└── .env.example
```

## Notes

- Voice input uses the browser Web Speech API and works best in Chrome or Edge.
- The cart is held in backend memory and resets when the backend restarts.
- The current cart implementation is intended for a demo and is not yet suitable for multiple backend workers or durable production orders.
- Short, specific requests with correctly spelled menu items produce the most reliable classifications.

## License

No license has been specified for this project yet.
