import os
import uuid
import datetime as dt
from flask import Flask, request, jsonify, abort
from sqlalchemy import create_engine, String, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from events import publish_event, start_consumer

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://msdemo:secret@postgres:5432/orders_db"
)

class Base(DeclarativeBase):
    pass

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(120))
    item: Mapped[str] = mapped_column(String(120))
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING|PAID|CANCELLED
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "item": self.item,
            "amount_cents": self.amount_cents,
            "status": self.status,
            "created_at": self.created_at.isoformat() + "Z",
        }

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base.metadata.create_all(engine)

app = Flask(__name__)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/orders")
def create_order():
    data = request.get_json(force=True) or {}
    name = (data.get("customer_name") or "").strip()
    item = (data.get("item") or "").strip()
    amount = int(data.get("amount_cents") or 0)

    if not name or not item or amount <= 0:
        abort(400, description="customer_name, item e amount_cents (>0) são obrigatórios")

    order = Order(
        id=str(uuid.uuid4()),
        customer_name=name,
        item=item,
        amount_cents=amount,
        status="PENDING",
    )

    with SessionLocal() as s:
        s.add(order)
        s.commit()

        resp = order.to_dict()

        payload = {
            "event": "order.created",
            "order_id": order.id,
            "customer_name": order.customer_name,
            "item": order.item,
            "amount_cents": order.amount_cents,
            "created_at": order.created_at.isoformat() + "Z",
        }

    publish_event("order.created", payload)
    return jsonify(resp), 201

@app.get("/orders")
def list_orders():
    with SessionLocal() as s:
        rows = s.query(Order).order_by(Order.created_at.desc()).all()
        return jsonify([o.to_dict() for o in rows])

@app.get("/orders/<order_id>")
def get_order(order_id: str):
    with SessionLocal() as s:
        obj = s.get(Order, order_id)
        if not obj:
            abort(404, description="order not found")
        return jsonify(obj.to_dict())

def _on_payment_event(message: dict):
    event = (message.get("event") or "").strip()
    order_id = (message.get("order_id") or "").strip()
    if not event or not order_id:
        return

    with SessionLocal() as s:
        obj = s.get(Order, order_id)
        if not obj:
            return

        if event == "payment.succeeded":
            if obj.status != "PAID":
                obj.status = "PAID"
                s.commit()
        elif event == "payment.failed":
            if obj.status == "PENDING":
                obj.status = "CANCELLED"
                s.commit()

start_consumer(
    queue="orders.payments",
    binding_keys=["payment.succeeded", "payment.failed"],
    handler=_on_payment_event
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
