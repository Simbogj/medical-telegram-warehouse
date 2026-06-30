# Medical Telegram Warehouse

An end-to-end ELT data platform that extracts medical business data from public Telegram channels, transforms it into an analytical warehouse, enriches image data using YOLOv8, and exposes insights through a REST API orchestrated by Dagster.

---

## Quick Start

```bash
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt
docker compose up -d
cp .env.example .env   # add Telegram + DB credentials
```

---

## Task 1 — Telegram Scraping

```bash
python src/scraper.py --demo --path data --limit 50   # no API keys
python src/scraper.py --path data --limit 500           # live Telethon
```

Output: `data/raw/telegram_messages/`, `data/raw/images/`, `logs/`

---

## Task 2 — dbt Warehouse

```bash
python src/load_to_postgres.py --path data
cd medical_warehouse
dbt run --profiles-dir .
dbt test --profiles-dir .
dbt docs generate --profiles-dir .
```

See [docs/INTERIM_REPORT.md](docs/INTERIM_REPORT.md) for star schema design.

---

## Task 3 — YOLO Enrichment

```bash
python src/yolo_detect.py --image-dir data/raw/images --output data/yolo_results.csv
python src/load_yolo_to_postgres.py --csv data/yolo_results.csv
cd medical_warehouse && dbt run --select fct_image_detections --profiles-dir .
```

Analysis write-up: [docs/TASK3_YOLO_ANALYSIS.md](docs/TASK3_YOLO_ANALYSIS.md)

**Image categories:** `promotional`, `product_display`, `lifestyle`, `other`

---

## Task 4 — Analytical API

```bash
uvicorn api.main:app --reload --port 8000
```

| Endpoint | Description |
|----------|-------------|
| `GET /api/reports/top-products?limit=10` | Most frequent product terms |
| `GET /api/channels/{channel_name}/activity` | Daily posting trends |
| `GET /api/search/messages?query=paracetamol` | Keyword search |
| `GET /api/reports/visual-content` | Image usage by channel |

OpenAPI docs: http://localhost:8000/docs

```bash
pytest tests/test_api.py -v
```

---

## Task 5 — Dagster Orchestration

```bash
dagster dev -f pipeline.py
```

Open http://localhost:3000 — run `medical_warehouse_job` manually or via the daily schedule (02:00 UTC).

Pipeline order: **scrape → load → dbt run → YOLO + load + fct_image_detections**

Set `SCRAPER_DEMO=true` (default) for demo mode without Telegram credentials.

---

## Branch Strategy

| Branch | Scope |
|--------|-------|
| `task-1` / `task-2` | Scraping + dbt foundation |
| `task3-yolo` | YOLO detection + `fct_image_detections` |
| `task4-analytics` | FastAPI analytical endpoints |
| `task5-dagster` | Full Dagster pipeline + CI |

---

## Environment Variables

```env
Tg_API_ID=
Tg_API_HASH=
DB_HOST=localhost
DB_PORT=5432
DB_NAME=telegram_warehouse
DB_USER=postgres
DB_PASSWORD=postgres
SCRAPER_DEMO=true
SCRAPER_LIMIT=100
YOLO_OUTPUT_CSV=data/yolo_results.csv
```

---

## Project Structure

```
medical-telegram-warehouse/
├── api/                  # Task 4 — FastAPI
├── medical_warehouse/    # Task 2/3 — dbt models
├── src/                  # Tasks 1/3 — scraper, loader, YOLO
├── pipeline.py           # Task 5 — Dagster
├── tests/                # API unit tests
├── docs/                 # Reports & analysis
└── data/                 # Data lake (gitignored)
```
