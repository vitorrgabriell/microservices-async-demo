import json
import os
import threading
import time
import pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672//")
EXCHANGE = "msdemo"

def _connection():
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)

def publish_event(routing_key: str, payload: dict):
    conn = _connection()
    try:
        ch = conn.channel()
        ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
        body = json.dumps(payload).encode("utf-8")
        ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
    finally:
        conn.close()

def start_consumer(queue: str, binding_keys: list[str], handler):
    def _run():
        while True:
            try:
                conn = _connection()
                ch = conn.channel()
                ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
                ch.queue_declare(queue=queue, durable=True)
                for key in binding_keys:
                    ch.queue_bind(exchange=EXCHANGE, queue=queue, routing_key=key)

                ch.basic_qos(prefetch_count=10)

                def _on_msg(chx, method, props, body):
                    try:
                        msg = json.loads(body.decode("utf-8"))
                        handler(msg)
                        chx.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception:
                        chx.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

                ch.basic_consume(queue=queue, on_message_callback=_on_msg)
                ch.start_consuming()
            except Exception:
                time.sleep(2)
                continue

    t = threading.Thread(target=_run, daemon=True)
    t.start()
