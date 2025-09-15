import json, os, threading, time, pika, logging
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")
EXCHANGE = "msdemo"

def _connection():
    return pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))

def publish_event(routing_key: str, payload: dict, max_retries: int = 8):
    delay = 0.5
    for attempt in range(1, max_retries + 1):
        try:
            conn = _connection()
            try:
                ch = conn.channel()
                ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
                ch.basic_publish(
                    exchange=EXCHANGE,
                    routing_key=routing_key,
                    body=json.dumps(payload).encode("utf-8"),
                    properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
                )
                return
            finally:
                conn.close()
        except Exception as e:
            logger.warning("publish_event falhou (tentativa %s/%s): %s", attempt, max_retries, e)
            time.sleep(delay)
            delay = min(delay * 2, 8)
    raise

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
                        handler(json.loads(body.decode("utf-8")))
                        chx.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception:
                        chx.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

                ch.basic_consume(queue=queue, on_message_callback=_on_msg)
                ch.start_consuming()
            except Exception as e:
                logger.warning("consumer desconectado: %s; tentando reconectar…", e)
                time.sleep(2)
                continue
    threading.Thread(target=_run, daemon=True).start()

def ensure_bindings(queue: str, binding_keys: list[str], max_retries: int = 30):
    delay = 0.5
    for attempt in range(1, max_retries + 1):
        try:
            conn = _connection()
            try:
                ch = conn.channel()
                ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
                ch.queue_declare(queue=queue, durable=True)
                for key in binding_keys:
                    ch.queue_bind(exchange=EXCHANGE, queue=queue, routing_key=key)
                logger.info("bindings OK (queue=%s, keys=%s)", queue, binding_keys)
                return True
            finally:
                conn.close()
        except Exception as e:
            logging.warning("ensure_bindings falhou (tentativa %s/%s): %s", attempt, max_retries, e)
            time.sleep(delay)
            delay = min(delay * 2, 8)
    logging.error("ensure_bindings: não conseguiu declarar após %s tentativas; seguindo sem bloquear", max_retries)
    return False
