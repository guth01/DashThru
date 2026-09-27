import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from huggingface_hub import InferenceClient, hf_hub_download
from pydantic import BaseModel, Field


MODEL_REPO = os.getenv("MODEL_REPO", "guth001/distilbert-drivethru-intent")
MODEL_CACHE = os.getenv("MODEL_CACHE", "/tmp/dashthru-model")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
HF_PROVIDER = os.getenv("HF_PROVIDER", "hf-inference")

REPLIES = {
    "order_item": "Great choice. Tell me the item and size you would like, and I’ll add it to your order.",
    "add_topping": "Absolutely. Which toppings would you like to add?",
    "ask_menu": "I can help with that. Ask me about a menu item, a veggie choice, or something spicy.",
    "checkout": "Your order is ready to check out. Would you like to confirm it?",
    "confirm": "Perfect — I’ve got that. Is there anything else you would like to add?",
    "cancel_item": "No problem. Tell me which item you would like me to remove.",
    "greeting": "Hi there! What can I get started for you today?",
    "other": "I’m ready to help with your order. Try asking for a menu item, a topping, or checkout.",
}


# Entity extraction is intentionally keyword/regex based for this lab demo.
MENU_CATALOG = {
    "Pizzas": ["pepperoni", "margherita", "veggie", "meat lovers", "cheese"],
    "Burgers": ["burger", "classic burger", "cheeseburger", "veggie burger"],
    "Coffee and drinks": ["latte", "cappuccino", "cold brew", "americano", "mocha", "coke", "sprite"],
    "Sides": ["fries", "garlic bread", "chicken wings", "garden salad", "mozzarella sticks"],
    "Desserts": ["brownie", "cheesecake", "chocolate cake", "ice cream"],
}

PIZZA_ITEMS = MENU_CATALOG["Pizzas"]
DRINK_ITEMS = MENU_CATALOG["Coffee and drinks"]
BURGER_ITEMS = MENU_CATALOG["Burgers"]
SIDE_ITEMS = MENU_CATALOG["Sides"]
DESSERT_ITEMS = MENU_CATALOG["Desserts"]
TOPPING_ITEMS = ["extra cheese", "mushrooms", "olives", "jalapenos", "bacon", "onions", "pineapple"]
# "burger" and "hamburger" aliases are supported for natural spoken requests.
MENU_ITEMS = PIZZA_ITEMS + BURGER_ITEMS + DRINK_ITEMS + SIDE_ITEMS + DESSERT_ITEMS + TOPPING_ITEMS
SIZES = ["extra large", "small", "medium", "large", "jumbo"]
BASE_MENU_ITEMS = set(PIZZA_ITEMS + BURGER_ITEMS + DRINK_ITEMS + SIDE_ITEMS + DESSERT_ITEMS)
NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
CONFIDENCE_THRESHOLD = 0.6
FALLBACK_REPLY = "I'm not sure exactly what you'd like - could you name a specific item, or ask me what's on the menu?"

# Lab-demo limitation: this state resets when the server restarts and is not safe
# as a production store or when running multiple backend workers.
cart_state: dict[str, dict[str, list[dict[str, Any]]]] = {}


def _phrase_pattern(phrase: str) -> str:
    """Build a word-boundary regex that accepts a simple plural."""
    parts = phrase.lower().replace("-", " ").split()
    last = parts[-1]
    if not last.endswith("s"):
        last = f"{last}s?"
    escaped = [re.escape(part) for part in parts[:-1]] + [last]
    return r"\b" + r"[\s-]+".join(escaped) + r"\b"


def _item_patterns() -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for item in sorted(MENU_ITEMS, key=len, reverse=True):
        aliases = [item]
        if item.endswith("s"):
            aliases.append(item[:-1])
        if item == "burger":
            aliases.extend(["hamburger", "hamburgers"])
        for alias in aliases:
            patterns.append((item, re.compile(_phrase_pattern(alias), re.IGNORECASE)))
    return patterns


ITEM_PATTERNS = _item_patterns()
SIZE_PATTERNS = [(size, re.compile(_phrase_pattern(size), re.IGNORECASE)) for size in SIZES]
QUANTITY_PATTERN = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


def _non_overlapping_matches(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> list[dict[str, Any]]:
    """Prefer longer phrases so 'extra cheese' does not also match 'cheese'."""
    matches: list[dict[str, Any]] = []
    for value, pattern in patterns:
        for match in pattern.finditer(text):
            if any(match.start() < existing["end"] and match.end() > existing["start"] for existing in matches):
                continue
            matches.append({"value": value, "start": match.start(), "end": match.end()})
    return sorted(matches, key=lambda match: match["start"])


def _quantity_value(raw_value: str) -> int:
    return max(1, int(raw_value)) if raw_value.isdigit() else NUMBER_WORDS.get(raw_value.lower(), 1)


def _nearest_before(matches: list[dict[str, Any]], start: int, window: int, text: str) -> dict[str, Any] | None:
    previous = []
    for match in matches:
        if match["end"] > start or start - match["end"] > window:
            continue
        between = text[match["end"]:start]
        # Do not inherit a quantity/size from a separate item phrase.
        if re.search(r"\b(?:and|or|then|plus)\b|[,;]", between):
            continue
        previous.append(match)
    return previous[-1] if previous else None


def extract_entities(text: str) -> dict[str, Any]:
    """Extract quantities, menu items, and sizes from a transcript."""
    normalized_text = re.sub(r"\s+", " ", text.lower().replace("-", " ")).strip()
    item_matches = _non_overlapping_matches(normalized_text, ITEM_PATTERNS)
    size_matches = _non_overlapping_matches(normalized_text, SIZE_PATTERNS)
    quantity_matches = [
        {"value": _quantity_value(match.group(1)), "start": match.start(), "end": match.end()}
        for match in QUANTITY_PATTERN.finditer(normalized_text)
    ]

    entities = []
    for item_match in item_matches:
        quantity_match = _nearest_before(quantity_matches, item_match["start"], window=32, text=normalized_text)
        size_match = _nearest_before(size_matches, item_match["start"], window=32, text=normalized_text)
        item = item_match["value"]
        if item not in BASE_MENU_ITEMS:
            size_match = None
        entities.append({
            "item": item,
            "quantity": quantity_match["value"] if quantity_match else 1,
            "size": size_match["value"] if size_match else None,
            "is_topping": item not in BASE_MENU_ITEMS,
            "start": item_match["start"],
        })

    return {
        "items": entities,
        "menu_items": [entity["item"] for entity in entities],
        "sizes": [match["value"] for match in size_matches],
        "quantities": [match["value"] for match in quantity_matches],
    }


def _correct_obvious_intent(text: str, model_intent: str, extracted: dict[str, Any]) -> str:
    """Apply small deterministic guardrails for unmistakable user commands.

    The classifier remains the primary intent model. These rules prevent a
    clear command such as 'checkout' or 'add extra cheese' from being blocked
    by an occasional ambiguous classifier label.
    """
    normalized = text.lower().strip()
    has_topping = any(entity["is_topping"] for entity in extracted["items"])
    has_base_item = any(not entity["is_topping"] for entity in extracted["items"])

    if re.search(r"\b(?:checkout|check out|pay|finish(?: my)? order|ready to pay)\b", normalized):
        return "checkout"
    if re.search(r"\b(?:cancel|remove|delete|take off)\b", normalized):
        return "cancel_item"
    if re.match(r"^(?:yes|yeah|yep|correct|that's right|that is right|confirm)\b", normalized):
        return "confirm"
    if re.match(r"^(?:hi|hello|hey|good morning|good afternoon|good evening)\b", normalized) and not has_base_item:
        return "greeting"
    if re.search(r"\b(?:menu|options|available|what do you have|what can i get)\b", normalized):
        return "ask_menu"
    if has_topping and re.search(r"\b(?:add|extra|with|without|no)\b", normalized):
        return "add_topping"
    if has_base_item and re.search(r"\b(?:order|want|would like|give me|get me|add)\b", normalized):
        return "order_item"
    if has_base_item and not has_topping and model_intent in {"order_item", "add_topping", "other"}:
        return "order_item"
    return model_intent


def _menu_reply() -> str:
    """Return the same menu categories that are displayed in the frontend."""
    lines = ["Here's what's on the menu:"]
    for category, items in MENU_CATALOG.items():
        lines.append(f"{category}: {', '.join(items)}")
    lines.append("Tell me an item, size, or topping whenever you're ready.")
    return "\n".join(lines)


def _get_cart(session_id: str) -> dict[str, list[dict[str, Any]]]:
    return cart_state.setdefault(session_id, {"items": [], "history": []})


def _item_label(item: str) -> str:
    return f"{item} pizza" if item in PIZZA_ITEMS else item


def _format_cart_item(item: dict[str, Any]) -> str:
    quantity = item["quantity"]
    size = f"{item['size']} " if item.get("size") else ""
    label = _item_label(item["item"])
    if quantity != 1 and not label.endswith("s"):
        label = f"{label}s"
    toppings = item.get("toppings", [])
    topping_text = f" with {', '.join(toppings)}" if toppings else ""
    return f"{quantity} {size}{label}{topping_text}"


def _cart_items(cart: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [dict(item, toppings=list(item.get("toppings", []))) for item in cart["items"]]


def _append_order_items(cart: dict[str, list[dict[str, Any]]], entities: list[dict[str, Any]]) -> str:
    base_entities = [entity for entity in entities if not entity["is_topping"]]
    topping_names = [entity["item"] for entity in entities if entity["is_topping"]]
    if not base_entities:
        return "I found a topping, but I need the menu item it should go on before adding it."

    added_lines = []
    for entity in base_entities:
        cart_item = {
            "item": entity["item"],
            "quantity": entity["quantity"],
            "size": entity["size"],
            "toppings": list(dict.fromkeys(topping_names)),
        }
        cart["items"].append(cart_item)
        added_lines.append(_format_cart_item(cart_item))
    return f"Got it - {', '.join(added_lines)} added to your order."


def _add_toppings(cart: dict[str, list[dict[str, Any]]], entities: list[dict[str, Any]]) -> str:
    topping_names = list(dict.fromkeys(entity["item"] for entity in entities if entity["is_topping"]))
    named_items = [entity["item"] for entity in entities if not entity["is_topping"]]
    if not topping_names:
        return "Which topping would you like to add?"

    target = None
    if named_items:
        for existing in reversed(cart["items"]):
            if existing["item"] in named_items:
                target = existing
                break
        if target is None:
            return f"I couldn't find {named_items[-1]} in your current order to add that topping to."
    elif cart["items"]:
        # No item was named: apply toppings to the most recently added item.
        target = cart["items"][-1]

    if target is None:
        return "Tell me which menu item you'd like the topping added to first."

    target_label_before = _format_cart_item(target)
    target["toppings"] = list(dict.fromkeys(target.get("toppings", []) + topping_names))
    return f"Got it - added {', '.join(topping_names)} to {target_label_before}."


def _cancel_item(cart: dict[str, list[dict[str, Any]]], entities: list[dict[str, Any]], text: str) -> str:
    requested_names = [entity["item"] for entity in entities]
    if not requested_names and re.search(r"\b(?:last|most recent)\b", text.lower()):
        if cart["items"]:
            removed = cart["items"].pop()
            return f"No problem - I removed {_format_cart_item(removed)} from your order."
        return "Your order is already empty, so there is nothing to cancel."

    for requested_name in reversed(requested_names):
        for index in range(len(cart["items"]) - 1, -1, -1):
            existing = cart["items"][index]
            if existing["item"] == requested_name:
                removed = cart["items"].pop(index)
                return f"No problem - I removed {_format_cart_item(removed)} from your order."
            if requested_name in existing.get("toppings", []):
                existing["toppings"].remove(requested_name)
                return f"No problem - I removed {requested_name} from {_format_cart_item(existing)}."
    return "I couldn't find anything matching that item in your order to remove."


def _checkout_reply(cart: dict[str, list[dict[str, Any]]]) -> str:
    if not cart["items"]:
        return "Your order is empty. Tell me what you'd like to add first."
    running_total = 0
    summary_lines = []
    for item in cart["items"]:
        running_total += item["quantity"]
        summary_lines.append(f"{_format_cart_item(item)} (running total: {running_total})")
    return f"Here's your order: {'; '.join(summary_lines)}. Total item count: {running_total}. Would you like to confirm?"


def _confirm_reply(cart: dict[str, list[dict[str, Any]]]) -> str:
    if not cart["items"]:
        return "I don't have an order to confirm yet. Tell me what you'd like to add first."
    total = sum(item["quantity"] for item in cart["items"])
    summary = "; ".join(_format_cart_item(item) for item in cart["items"])
    return f"Confirmed - I've got {summary}. Total item count: {total}."


def load_label_maps():
    """Read the optional label mapping without downloading model weights."""
    mapping = {}
    local_mapping = Path(MODEL_CACHE) / "intent_labels.json"
    try:
        mapping_path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename="intent_labels.json",
            cache_dir=MODEL_CACHE,
            token=HF_TOKEN,
        )
        local_mapping = Path(mapping_path)
    except Exception:
        # A config.json id2label mapping is still available if the optional
        # artifact is absent from a model repo.
        pass
    if local_mapping.exists():
        with local_mapping.open(encoding="utf-8") as file:
            mapping = json.load(file)
    labels = mapping.get("id2label", {})
    if labels:
        return {int(key): value for key, value in labels.items()}
    return {index: label for index, label in enumerate(REPLIES)}


def _normalize_model_intent(raw_label: str) -> str:
    """Convert provider labels such as LABEL_0 into the app's intent names."""
    label = str(raw_label).strip()
    normalized = label.lower().replace("-", "_").replace(" ", "_")
    if normalized in REPLIES:
        return normalized

    numeric_label = re.fullmatch(r"label[_-]?(\d+)", normalized)
    if numeric_label:
        return id2label.get(int(numeric_label.group(1)), "other")
    return "other"


app = FastAPI(title="DashThru Voice Ordering API", version="1.0.0")
origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

inference_client = None
id2label = {}


@app.on_event("startup")
def load_inference_client():
    global inference_client, id2label
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN is required for remote Hugging Face inference")
    inference_client = InferenceClient(
        model=MODEL_REPO,
        provider=HF_PROVIDER,
        token=HF_TOKEN,
    )
    id2label = load_label_maps()


class PredictRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    session_id: str = Field(min_length=1, max_length=128)


class CartItem(BaseModel):
    item: str
    quantity: int = Field(ge=1)
    size: str | None = None
    toppings: list[str] = Field(default_factory=list)


class PredictResponse(BaseModel):
    reply: str
    intent: str
    confidence: float
    cart: list[CartItem]


@app.get("/")
def health_check():
    return {"service": "DashThru voice ordering API", "status": "ok"}


def _classify_with_huggingface(text: str) -> tuple[str, float]:
    """Classify text through Hugging Face without loading model weights locally."""
    if inference_client is None:
        raise HTTPException(status_code=503, detail="Hugging Face inference is not configured")

    try:
        results = inference_client.text_classification(text, model=MODEL_REPO)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Hugging Face inference request failed") from error

    if not results:
        raise HTTPException(status_code=502, detail="Hugging Face returned no classification")

    best_result = max(results, key=lambda result: float(result.score))
    return _normalize_model_intent(best_result.label), float(best_result.score)


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    cart = _get_cart(request.session_id)
    model_intent, confidence = _classify_with_huggingface(request.text)
    extracted = extract_entities(request.text)
    intent = _correct_obvious_intent(request.text, model_intent, extracted)

    # Always keep a lightweight transcript for this demo session, including
    # requests that fall below the confidence threshold.
    history_entry = {
        "text": request.text,
        "intent": intent,
        "model_intent": model_intent,
        "confidence": round(confidence, 4),
    }
    cart["history"].append(history_entry)

    # Do not mutate the cart based on a weak prediction or an order guess with
    # no real menu item in the transcript. This handles "something spicy".
    is_entity_required_intent = intent in {"order_item", "add_topping"}
    explicit_guardrail = intent != model_intent
    if (confidence < CONFIDENCE_THRESHOLD and not explicit_guardrail) or (is_entity_required_intent and not extracted["items"]):
        reply = FALLBACK_REPLY
    elif intent == "order_item":
        reply = _append_order_items(cart, extracted["items"])
    elif intent == "add_topping":
        reply = _add_toppings(cart, extracted["items"])
    elif intent == "cancel_item":
        reply = _cancel_item(cart, extracted["items"], request.text)
    elif intent == "checkout":
        reply = _checkout_reply(cart)
    elif intent == "confirm":
        reply = _confirm_reply(cart)
    elif intent == "ask_menu":
        reply = _menu_reply()
    else:
        reply = REPLIES.get(intent, REPLIES["other"])

    return PredictResponse(
        reply=reply,
        intent=intent,
        confidence=round(confidence, 4),
        cart=[CartItem(**item) for item in _cart_items(cart)],
    )
