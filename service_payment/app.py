import os, uuid, random, datetime as dt, threading, logging
from flask import Flask, request, jsonify, abort
from events import publish_event, start_consumer, ensure_bindings

logging.basicConfig(level=logging.INFO)
PAYMENT_CONSUMER_ENABLED = os.getenv("PAYMENT_CONSUMER_ENABLED", "true").lower() in ("1","true","yes")
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.get("/health")
def health():
    return {"status": "ok"}

def _pay(order_id: str, amount_cents: int) -> dict:
    status = "SUCCESS" if amount_cents > 0 else "FAILED"
    event_key = "payment.succeeded" if status == "SUCCESS" else "payment.failed"
    payload = {
        "event": event_key,
        "order_id": order_id,
        "payment_id": str(uuid.uuid4()),
        "amount_cents": amount_cents,
        "at": dt.datetime.utcnow().isoformat() + "Z",
        "idempotency_key": order_id,
    }
    publish_event(event_key, payload)
    return payload

@app.post("/payments")
def create_payment():
    data = request.get_json(force=True) or {}
    order_id = (data.get("order_id") or "").strip()
    amount = int(data.get("amount_cents") or 0)
    if not order_id or amount <= 0:
        abort(400, description="order_id e amount_cents (>0) são obrigatórios")
    payload = _pay(order_id, amount)
    return jsonify(payload), 201

def _on_order_created(msg: dict):
    if (msg.get("event") or "") != "order.created":
        return
    order_id = (msg.get("order_id") or "").strip()
    amount = int(msg.get("amount_cents") or 0)
    if not order_id:
        return
    _pay(order_id, amount)

_CONSUMER_STARTED = False

def _bootstrap_broker_async():
    def runner():
        global _CONSUMER_STARTED
        ok = ensure_bindings(queue="payments.orders", binding_keys=["order.created"])
        if PAYMENT_CONSUMER_ENABLED and not _CONSUMER_STARTED:
            start_consumer(queue="payments.orders", binding_keys=["order.created"], handler=_on_order_created)
            _CONSUMER_STARTED = True
            logger.info("consumer 'order.created' iniciado (enabled=%s, bindings_ok=%s)", PAYMENT_CONSUMER_ENABLED, ok)
        else:
            logger.info("consumer DESLIGADO (enabled=%s); bindings_ok=%s", PAYMENT_CONSUMER_ENABLED, ok)
    threading.Thread(target=runner, daemon=True).start()

_bootstrap_broker_async()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
