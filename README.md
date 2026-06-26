# Medical Telegram Warehouse

An end-to-end ELT data platform that extracts medical business data from public Telegram channels, transforms it into an analytical warehouse, enriches image data using object detection, and exposes insights through a REST API.

---

## Project Overview

This project builds a modern data pipeline for collecting, transforming, enriching, and serving analytical insights from Ethiopian medical-related Telegram channels.

The platform:

* Extracts Telegram messages and media
* Stores raw data in a Data Lake
* Loads data into PostgreSQL

---

# Project Structure

```plaintext
medical-telegram-warehouse/

├── api/
│   
├── data/
│   ├── raw/
│   │   ├── images/
│   │   └── telegram_messages/
├── logs/
├── medical_warehouse/
├── notebooks/
├── scripts/
├── src/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── .env
```

---

# Environment Setup

## Clone Repository

```bash
git clone https://github.com/Simbogj/medical-telegram-warehouse.git
cd medical-telegram-warehouse
```

## Create Virtual Environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

Linux/Mac:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# Environment Variables

Create `.env`

```env
API_ID=MY_TELEGRAM_API
API_HASH=HASH

DB_USER=postgres
DB_PASSWORD=******
DB_HOST=localhost
DB_PORT=5432
DB_NAME=telegram_warehouse
```

---

# Task 1 — Telegram Data Collection

Run scraper:

```bash
python src/scraper.py
```

Output:

```plaintext
data/raw/telegram_messages/
data/raw/images/
logs/
```

Collected fields:

* message_id
* channel_name
* message_date
* message_text
* views
* forwards
* image_path

---

# Task 2 — Data Warehouse and dbt

Load raw data:

```bash
python src/load_raw.py
```

Initialize dbt:

```bash
dbt init medical_warehouse
```

Run models:

```bash
dbt run
```

Run tests:

```bash
dbt test
```

Generate documentation:

```bash
dbt docs generate
dbt docs serve
```

---

# Star Schema

## Dimensions

### dim_channels

* channel_key
* channel_name
* channel_type
* total_posts
* avg_views

### dim_dates

* date_key
* month
* quarter
* year
* week

## Facts

### fct_messages

* message_id
* channel_key
* date_key
* message_text
* message_length
* views
* forwards

### fct_image_detections

* message_id
* detected_class
* confidence_score
* image_category

---

# Future Work

* Task 3 — Data Enrichment with Object Detection (YOLO) 
* Task 4 — Build an Analytical API
* Task 5 — Pipeline Orchestration

---