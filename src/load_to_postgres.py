"""
Task 2 — Load raw Telegram JSON data into PostgreSQL

Loads:
    data/raw/telegram_messages/YYYY-MM-DD/*.json

Into:
    raw.telegram_messages

Optional:
    data/yolo_results.csv
    → raw.yolo_detections

Usage:
    docker compose up -d
    python src/load_to_postgres.py --path data
"""

import os
import json
import glob
import csv
import argparse
import logging

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# =====================================================
# CONFIG
# =====================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("load_to_postgres")


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "telegram_warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

DATABASE_URL = (
    f"postgresql://"
    f"{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}"
    f"/{DB_NAME}"
)


# =====================================================
# CONNECTION
# =====================================================

def get_engine():
    return create_engine(DATABASE_URL)


# =====================================================
# RAW TABLE
# =====================================================

def create_raw_table(engine):

    with engine.begin() as conn:

        conn.execute(text("""
            CREATE SCHEMA IF NOT EXISTS raw
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS raw.telegram_messages (

                message_id INTEGER,

                channel_name TEXT,

                channel_title TEXT,

                message_date TIMESTAMP,

                message_text TEXT,

                has_media BOOLEAN,

                image_path TEXT,

                views INTEGER,

                forwards INTEGER

            )
        """))

        conn.execute(text("""
            TRUNCATE TABLE raw.telegram_messages
        """))

    logger.info(
        "raw.telegram_messages ready"
    )


# =====================================================
# LOAD JSON
# =====================================================

def load_json_files(
    engine,
    data_path,
):

    pattern = os.path.join(

        data_path,

        "raw",

        "telegram_messages",

        "*",

        "*.json",

    )

    files = [

        f

        for f in glob.glob(pattern)

        if not f.endswith(
            "_manifest.json"
        )

    ]

    if not files:

        logger.warning(
            "No JSON files found"
        )

        return 0

    total = 0

    with engine.begin() as conn:

        for file in sorted(files):

            logger.info(
                f"Reading {file}"
            )

            with open(
                file,
                "r",
                encoding="utf-8",
            ) as f:

                messages = json.load(f)
                if not messages:
                    logger.warning(
                        f"Skipping empty dataset: {file}"
                        )
                    continue

            for msg in messages:

                conn.execute(

                    text("""
                        INSERT INTO raw.telegram_messages (

                            message_id,
                            channel_name,
                            channel_title,
                            message_date,
                            message_text,
                            has_media,
                            image_path,
                            views,
                            forwards

                        )

                        VALUES (

                            :message_id,
                            :channel_name,
                            :channel_title,
                            :message_date,
                            :message_text,
                            :has_media,
                            :image_path,
                            :views,
                            :forwards

                        )
                    """),

                    {

                        "message_id":
                        msg.get(
                            "message_id"
                        ),

                        "channel_name":
                        msg.get(
                            "channel_name"
                        ),

                        "channel_title":
                        msg.get(
                            "channel_title",
                            ""
                        ),

                        "message_date":
                        msg.get(
                            "message_date"
                        ),

                        "message_text":
                        msg.get(
                            "message_text",
                            ""
                        ),

                        "has_media":
                        msg.get(
                            "has_media",
                            False
                        ),

                        "image_path":
                        msg.get(
                            "image_path"
                        ),

                        "views":
                        msg.get(
                            "views",
                            0
                        ),

                        "forwards":
                        msg.get(
                            "forwards",
                            0
                        ),

                    }

                )

            logger.info(
                f"Loaded {len(messages)} rows"
            )

            total += len(
                messages
            )

    logger.info(
        f"Total loaded: {total}"
    )

    return total


# =====================================================
# YOLO
# =====================================================

def load_yolo_results(

    engine,

    csv_path="data/yolo_results.csv",

):

    if not os.path.exists(
        csv_path
    ):

        logger.info(
            "YOLO CSV not found — skipping"
        )

        return

    with engine.begin() as conn:

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS raw.yolo_detections (

                image_path TEXT,

                message_id INTEGER,

                channel_name TEXT,

                detected_class TEXT,

                confidence FLOAT,

                image_category TEXT

            )
        """))

        conn.execute(text("""
            TRUNCATE TABLE raw.yolo_detections
        """))

        with open(
            csv_path,
            encoding="utf-8",
        ) as f:

            reader = csv.DictReader(
                f
            )

            for row in reader:

                conn.execute(

                    text("""
                        INSERT INTO raw.yolo_detections
                        VALUES (

                            :image_path,
                            :message_id,
                            :channel_name,
                            :detected_class,
                            :confidence,
                            :image_category

                        )
                    """),

                    {

                        "image_path":
                        row[
                            "image_path"
                        ],

                        "message_id":
                        int(
                            row[
                                "message_id"
                            ]
                        ),

                        "channel_name":
                        row[
                            "channel_name"
                        ],

                        "detected_class":
                        row[
                            "detected_class"
                        ],

                        "confidence":
                        float(
                            row[
                                "confidence"
                            ]
                        ),

                        "image_category":
                        row[
                            "image_category"
                        ],

                    }

                )

    logger.info(
        "YOLO results loaded"
    )


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(

        "--path",

        default="data",

        type=str,

    )

    args = parser.parse_args()

    engine = get_engine()

    create_raw_table(
        engine
    )

    load_json_files(
        engine,
        args.path,
    )

    load_yolo_results(
        engine
    )

    logger.info(
        "Task 2 completed"
    )