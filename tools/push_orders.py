import argparse, asyncio, random, string
import httpx

ITEMS = [
    "Curso Flask Pro", "Python Essencial", "Arquitetura de Microsserviços",
    "RabbitMQ do Zero", "FastAPI Hands-on", "SQL Performance"
]

def rand_suffix(n=6):
    import secrets
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))

def pick_item(): return random.choice(ITEMS)
def pick_amount(): return random.choice([1990, 4990, 9900, 12900])

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order-base-url", default="http://localhost:8001")
    ap.add_argument("--total", type=int, default=50)
    ap.add_argument("--concurrency", type=int, default=10)
    args = ap.parse_args()

    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:
        async def one():
            async with sem:
                payload = {
                    "customer_name": f"Vitor-{rand_suffix()}",
                    "item": pick_item(),
                    "amount_cents": pick_amount()
                }
                r = await client.post(f"{args.order_base_url}/orders", json=payload, timeout=5.0)
                ok = "OK" if r.status_code == 201 else f"ERR({r.status_code})"
                return ok

        results = await asyncio.gather(*[one() for _ in range(args.total)])
    print(f"Criados: {results.count('OK')}/{len(results)}")

if __name__ == "__main__":
    asyncio.run(main())
