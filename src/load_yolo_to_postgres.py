"""
Load YOLO detection CSV into raw.image_detections for dbt consumption.

Usage:
    python src/load_yolo_to_postgres.py
    python src/load_yolo_to_postgres.py --csv data/yolo_results.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
logger = logging.getLogger("load_yolo_to_postgres")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "telegram_warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

DEFAULT_CSV = os.getenv("YOLO_OUTPUT_CSV", "data/yolo_results.csv")


def get_engine():
    return create_engine(DATABASE_URL)


def create_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS raw.image_detections (
                image_path TEXT,
                message_id INTEGER,
                channel_name TEXT,
                detected_class TEXT,
                confidence_score DOUBLE PRECISION,
                image_category TEXT
            )
        """))
        conn.execute(text("TRUNCATE TABLE raw.image_detections"))


def load_csv(engine, csv_path: str) -> int:
    if not os.path.exists(csv_path):
        logger.warning("YOLO CSV not found: %s", csv_path)
        return 0

    total = 0
    with engine.begin() as conn:
        with open(csv_path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                message_id = row.get("message_id") or None
                conn.execute(
                    text("""
                        INSERT INTO raw.image_detections (
                            image_path,
                            message_id,
                            channel_name,
                            detected_class,
                            confidence_score,
                            image_category
                        ) VALUES (
                            :image_path,
                            :message_id,
                            :channel_name,
                            :detected_class,
                            :confidence_score,
                            :image_category
                        )
                    """),
                    {
                        "image_path": row.get("image_path"),
                        "message_id": int(message_id) if message_id else None,
                        "channel_name": row.get("channel_name"),
                        "detected_class": row.get("detected_class"),
                        "confidence_score": float(row.get("confidence_score") or 0),
                        "image_category": row.get("image_category"),
                    },
                )
                total += 1

    logger.info("Loaded %d YOLO records into raw.image_detections", total)
    return total


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV)
    args = parser.parse_args()

    engine = get_engine()
    create_table(engine)
    load_csv(engine, args.csv)


if __name__ == "__main__":
    main()
