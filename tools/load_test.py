# tools/load_test.py
import argparse, asyncio, random, string, time
from dataclasses import dataclass
from typing import List, Optional
import httpx


def parse_args():
    p = argparse.ArgumentParser(description="Load test for async microservices (Order ↔ RabbitMQ ↔ Payment)")
    p.add_argument("--order-base-url", default="http://localhost:8001", help="Base URL do service_order")
    p.add_argument("--total", type=int, default=50, help="Qtde total de pedidos")
    p.add_argument("--concurrency", type=int, default=10, help="Nível de concorrência")
    p.add_argument("--fail-rate", type=float, default=0.1, help="Probabilidade (0..1) de gerar amount_cents=0 (falha)")
    p.add_argument("--timeout-sec", type=float, default=10.0, help="Timeout para o pedido atingir estado final")
    p.add_argument("--rabbit-api", default="http://localhost:15672/api", help="URL base do RabbitMQ Management API")
    p.add_argument("--rabbit-user", default="msdemo")
    p.add_argument("--rabbit-pass", default="secret")
    p.add_argument("--check-queues", action="store_true", help="Faz leitura de filas via Rabbit API antes/depois")
    return p.parse_args()


ITEMS = [
    "Curso Flask Pro", "Python Essencial", "Arquitetura de Microsserviços",
    "RabbitMQ do Zero", "FastAPI Hands-on", "SQL Performance"
]

def rand_suffix(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def pick_item():
    return random.choice(ITEMS)

def pick_amount(fail_rate: float):
    if random.random() < fail_rate:
        return 0
    return random.choice([1990, 4990, 9900, 12900])

@dataclass
class Result:
    order_id: Optional[str]
    expected: str
    final_status: Optional[str]
    create_code: int
    t_create_ms: float
    t_e2e_ms: Optional[float]
    error: Optional[str] = None


async def get_queue_depth(client: httpx.AsyncClient, api_base: str, auth, vhost: str, queue: str) -> Optional[int]:
    try:
        vhost_enc = "%2F" if vhost == "/" else vhost
        r = await client.get(f"{api_base}/queues/{vhost_enc}/{queue}", auth=auth, timeout=5.0)
        if r.status_code == 200:
            return int(r.json().get("messages", 0))
    except Exception:
        pass
    return None


async def create_order_and_wait(i: int, order_base_url: str, fail_rate: float, timeout_sec: float, client: httpx.AsyncClient) -> Result:
    customer = f"Vitor-{rand_suffix()}"
    item = pick_item()
    amount = pick_amount(fail_rate)
    expected = "PAID" if amount > 0 else "CANCELLED"

    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{order_base_url}/orders",
            json={"customer_name": customer, "item": item, "amount_cents": amount},
            timeout=5.0,
        )
        t_create_ms = (time.perf_counter() - t0) * 1000
    except Exception as e:
        return Result(None, expected, None, -1, 0.0, None, error=f"create_exc: {e}")

    order_id = None
    if r.status_code == 201:
        order_id = r.json().get("id")

    final_status = None
    t_e2e_ms = None
    t_start = time.perf_counter()
    deadline = t_start + timeout_sec
    while time.perf_counter() < deadline and order_id:
        try:
            g = await client.get(f"{order_base_url}/orders/{order_id}", timeout=5.0)
            if g.status_code == 200:
                final_status = g.json().get("status")
                if final_status == expected:
                    t_e2e_ms = (time.perf_counter() - t0) * 1000
                    break
        except Exception:
            pass
        await asyncio.sleep(0.2)

    return Result(order_id, expected, final_status, r.status_code, t_create_ms, t_e2e_ms,
                  error=None if r.status_code == 201 else f"create_status={r.status_code}")

async def run_load(args):
    limits = httpx.Limits(max_connections=args.concurrency)
    async with httpx.AsyncClient(limits=limits) as client:
        if args.check_queues:
            before_po = await get_queue_depth(client, args.rabbit_api, (args.rabbit_user, args.rabbit_pass), "/", "payments.orders")
            before_op = await get_queue_depth(client, args.rabbit_api, (args.rabbit_user, args.rabbit_pass), "/", "orders.payments")
            print(f"[RabbitMQ] before  payments.orders={before_po}  orders.payments={before_op}")

        sem = asyncio.Semaphore(args.concurrency)
        results: List[Result] = []

        async def worker(idx: int):
            async with sem:
                res = await create_order_and_wait(idx, args.order_base_url, args.fail_rate, args.timeout_sec, client)
                results.append(res)

        await asyncio.gather(*(worker(i) for i in range(args.total)))

        if args.check_queues:
            after_po = await get_queue_depth(client, args.rabbit_api, (args.rabbit_user, args.rabbit_pass), "/", "payments.orders")
            after_op = await get_queue_depth(client, args.rabbit_api, (args.rabbit_user, args.rabbit_pass), "/", "orders.payments")
            print(f"[RabbitMQ] after   payments.orders={after_po}  orders.payments={after_op}")

    ok_create = sum(1 for r in results if r.create_code == 201)
    timeouts = [r for r in results if r.t_e2e_ms is None]
    paid = sum(1 for r in results if r.final_status == "PAID")
    cancelled = sum(1 for r in results if r.final_status == "CANCELLED")

    e2e = sorted([r.t_e2e_ms for r in results if r.t_e2e_ms is not None])
    def pct(p):
        if not e2e: return None
        k = max(0, min(len(e2e)-1, int(round((p/100)*len(e2e)))-1))
        return e2e[k]

    print("\n==== SUMMARY =====================================")
    print(f"Total reqs           : {args.total}")
    print(f"Concurrency          : {args.concurrency}")
    print(f"Fail rate (injected) : {args.fail_rate:.0%}")
    print(f"Creates 201          : {ok_create}/{args.total}")
    print(f"Final PAID           : {paid}")
    print(f"Final CANCELLED      : {cancelled}")
    print(f"Timeouts             : {len(timeouts)}")
    if e2e:
        print(f"E2E latency (ms)     : p50={pct(50):.1f}  p95={pct(95):.1f}  min={min(e2e):.1f}  max={max(e2e):.1f}")
    else:
        print("E2E latency          : (sem dados)")
    print("==================================================\n")

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_load(args))
