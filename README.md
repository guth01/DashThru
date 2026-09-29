# DashThru

> A voice-first drive-thru ordering assistant for quick, natural food orders.

## Submission links

- **Live application:** [https://dashthru-web.onrender.com/](https://dashthru-web.onrender.com/)
- **Hugging Face model and dataset reference:** [distilbert-drivethru-intent](https://huggingface.co/guth001/distilbert-drivethru-intent/tree/main)
- **Source code:** [GitHub repository](https://github.com/guth01/DashThru)

DashThru combines a React/Vite interface with a FastAPI backend and a fine-tuned DistilBERT intent classifier. Customers can speak or type an order, browse the menu, customize items, remove items, and check out through one conversation.

## At a glance

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | React + Vite | Voice and text ordering interface |
| Backend | FastAPI + Uvicorn | Prediction API and cart logic |
| Model | Fine-tuned DistilBERT loaded from Hugging Face Hub | Local intent classification |
| Deployment | Render | Live frontend hosting |

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
uvicorn app:app --reload --host 0.0.0.0 --port 7860
```

The backend downloads and loads `guth001/distilbert-drivethru-intent` locally at startup, then performs CPU-only inference in the API process.

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

The application is publicly deployed at [https://dashthru-web.onrender.com/](https://dashthru-web.onrender.com/). The backend runs as a Render native Python web service, while the frontend is served as a Render static site.

### Recommended deployment

```text
Render Web Service  -> FastAPI backend
Render Static Site  -> React/Vite frontend
Hugging Face        -> DistilBERT model and dataset reference
```

For the backend Render Web Service, set the root directory to `backend` and enter these values manually:

```text
Runtime: Python 3
Python version: 3.11.11 (set PYTHON_VERSION=3.11.11)
Build Command: pip install -r requirements.txt
Start Command: uvicorn app:app --host 0.0.0.0 --port $PORT
Health Check Path: /
```

Set these environment variables:

```text
MODEL_REPO=guth001/distilbert-drivethru-intent
CORS_ORIGINS=https://dashthru-web.onrender.com
```

`HF_TOKEN` is only needed if the model repository is private or gated. The model is downloaded into the instance's temporary cache during startup, so a restart or free-tier sleep can trigger another download and model load.

For the frontend, build with:

```text
npm ci && npm run build
```

and set:

```text
VITE_API_URL=<deployed-backend-url>
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_URL` | `http://localhost:7860` | Frontend API base URL |
| `MODEL_REPO` | `guth001/distilbert-drivethru-intent` | Hugging Face model repository |
| `MODEL_CACHE` | `/tmp/dashthru-model` | Temporary cache for the optional label mapping |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins |
| `HF_TOKEN` | unset | Optional Hugging Face token for private or gated model repositories |

## Project structure

```text
.
├── src/                  # React application and styles
├── backend/
│   ├── app.py            # FastAPI API and ordering logic
│   └── requirements.txt  # Python dependencies
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
