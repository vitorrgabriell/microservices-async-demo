
# 🚀 Microservices Async Demo

Projeto didático que demonstra uma arquitetura moderna de **microserviços assíncronos** usando Python, Docker, RabbitMQ e PostgreSQL. Ideal para quem deseja aprender sobre comunicação desacoplada, eventos e escalabilidade em sistemas distribuídos.


## 🛠️ Tecnologias

- **Python 3.11** — Linguagem principal dos microserviços
- **Flask** — Framework web para APIs REST
- **SQLAlchemy** — ORM para integração com bancos de dados
- **Docker & Docker Compose** — Containerização e orquestração dos serviços
- **RabbitMQ** — Mensageria para comunicação assíncrona entre microserviços
- **PostgreSQL** — Banco de dados relacional


## 📦 Estrutura do Projeto

- `service_order/` — Gerenciamento de pedidos
- `service_payment/` — Processamento de pagamentos
- `ops/postgres/` — Scripts de inicialização do banco de dados
- `tools/` — Scripts para testes e automação
- `docker-compose.yml` — Orquestração dos serviços


## 🔗 Comunicação entre Serviços

Os microserviços trocam eventos via RabbitMQ, utilizando tópicos para garantir escalabilidade e desacoplamento:

- **service_order** publica eventos de criação de pedidos
- **service_payment** consome eventos, processa pagamentos e publica resultados

## ⚡ Como Executar

1. Clone o repositório:
  ```bash
  git clone <url-do-repositorio>
  cd microservices-async-demo
  ```
2. Copie o arquivo de exemplo de variáveis de ambiente:
  ```bash
  cp .env.example .env
  ```
3. Inicie os serviços:
  ```bash
  docker-compose up --build
  ```
4. Acesse os endpoints REST dos serviços para criar pedidos e pagamentos.

## 🧪 Scripts Úteis

- `tools/drain_payments.py` — Processa pagamentos pendentes
- `tools/load_test.py` — Teste de carga dos serviços
- `tools/push_orders.py` — Gera pedidos para testes

## 🗄️ Banco de Dados

O PostgreSQL é inicializado automaticamente com os scripts em `ops/postgres/init/01-init.sql`.

## 📚 Exemplos de Uso

### Consultar pedidos
```bash
curl http://localhost:8001/orders
```

### Criar um pedido
```bash
curl -X POST http://localhost:8001/orders -H "Content-Type: application/json" -d '{"customer_name": "User Test", "item": "Product X", "amount_cents": 1500}'
```

### Realizar um pagamento
```bash
curl -X POST http://localhost:8002/payments -H "Content-Type: application/json" -d '{"order_id": <id do pedido>, "amount_cents": 1500}'
```

---
