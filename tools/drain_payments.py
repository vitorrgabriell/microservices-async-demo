import argparse, json, time, uuid, datetime as dt
import pika

def main():
    ap = argparse.ArgumentParser(description="Consome 'payments.orders' (order.created) e publica 'payment.succeeded'")
    ap.add_argument("--amqp-url", default="amqp://msdemo:secret@localhost:5672/%2F")
    ap.add_argument("--exchange", default="msdemo")
    ap.add_argument("--queue", default="payments.orders")
    ap.add_argument("--binding", default="order.created")
    ap.add_argument("--max", type=int, default=0, help="Máximo de mensagens para drenar (0 = tudo)")
    ap.add_argument("--sleep", type=float, default=0.0, help="Sleep entre mensagens (s)")
    args = ap.parse_args()

    conn = pika.BlockingConnection(pika.URLParameters(args.amqp_url))
    ch = conn.channel()

    ch.exchange_declare(exchange=args.exchange, exchange_type="topic", durable=True)
    ch.queue_declare(queue=args.queue, durable=True)
    ch.queue_bind(exchange=args.exchange, queue=args.queue, routing_key=args.binding)

    drained = 0
    while True:
        method, properties, body = ch.basic_get(queue=args.queue, auto_ack=False)
        if method is None:
            print("Fila vazia.")
            break

        try:
            msg = json.loads(body.decode("utf-8"))
            order_id = msg.get("order_id")
            amount = int(msg.get("amount_cents") or 0)
            payload = {
                "event": "payment.succeeded",
                "order_id": order_id,
                "payment_id": str(uuid.uuid4()),
                "amount_cents": amount,
                "at": dt.datetime.utcnow().isoformat() + "Z",
                "idempotency_key": order_id
            }
            ch.basic_publish(
                exchange=args.exchange,
                routing_key="payment.succeeded",
                body=json.dumps(payload).encode("utf-8"),
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            drained += 1
            if args.sleep > 0:
                time.sleep(args.sleep)
            if args.max and drained >= args.max:
                print(f"Parando por --max={args.max}")
                break
        except Exception as e:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            print("Erro processando mensagem, requeue:", e)

    conn.close()
    print(f"Drained: {drained}")

if __name__ == "__main__":
    main()
