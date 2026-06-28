"""
Telegram Scraper for Ethiopian Medical & Pharmaceutical Channels
=============================================================
Scrapes public Telegram channels and stores:
- Raw messages as JSON (partitioned by date): data/raw/telegram_messages/YYYY-MM-DD/channel.json
- Images: data/raw/images/{channel_name}/{message_id}.jpg
- CSV backup: data/raw/csv/YYYY-MM-DD/telegram_data.csv
- Logs: logs/scrape_YYYY-MM-DD.log

Usage:
    python src/telegram_scraper.py --demo --path data --limit 50
    python src/telegram_scraper.py --path data --limit 500   # live Telegram auth
"""

import os
import csv
import json
import asyncio
import argparse
import logging
import random
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from dotenv import load_dotenv



# PROJECT_ROOT = Path(__file__).resolve().parents[1]
# if str(PROJECT_ROOT) not in sys.path:
#     sys.path.insert(0, str(PROJECT_ROOT))

# from src.datalake import write_channel_messages_json, write_manifest


# ------------------------------------------------ # 
# ENVIRONMENT
# ------------------------------------------------

load_dotenv()

# API_ID = os.getenv("Tg_API_ID") 
# API_HASH = os.getenv("Tg_API_HASH") 

api_id_str = os.getenv("Tg_API_ID")
api_hash = os.getenv("Tg_API_HASH")

TODAY = datetime.today().strftime("%Y-%m-%d")

DEFAULT_CHANNEL_DELAY = 3.0
DEFAULT_MESSAGE_DELAY = 1.0

# ------------------------------------------------ 
# PATHS 
# ------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1] 
LOG_DIR = PROJECT_ROOT / "logs" 
LOG_DIR.mkdir(exist_ok=True)

# LOG_DIR = "logs"
# os.makedirs(LOG_DIR, exist_ok=True)

# ------------------------------------------------ 
# LOGGING
# ------------------------------------------------

logger = logging.getLogger("telegram_scraper")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s" 
    ) 
file_handler = logging.FileHandler(
    LOG_DIR / f"scrape_{TODAY}.log", encoding="utf8" 
    )

file_handler.setFormatter(formatter) 
console = logging.StreamHandler() 
console.setFormatter(formatter) 
logger.addHandler(file_handler) 
logger.addHandler(console)


console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))


# ------------------------------------------------
# SAVE HELPERS
# ------------------------------------------------

def write_channel_messages_json(
    base_path,
    date_str,
    channel_name,
    messages,
):

    output_dir = os.path.join(
        base_path,
        "raw",
        "telegram_messages",
        date_str,
    )

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    output_file = os.path.join(
        output_dir,
        f"{channel_name}.json",
    )

    with open(
        output_file,
        "w",
        encoding="utf8",
    ) as f:

        json.dump(
            messages,
            f,
            ensure_ascii=False,
            indent=2,
        )


def write_manifest(
    base_path,
    date_str,
    channel_message_counts,
):

    manifest = {

        "scrape_date":
        date_str,

        "channels":
        channel_message_counts,

        "total_messages":
        sum(
            channel_message_counts.values()
        ),

    }

    output = os.path.join(
        base_path,
        "raw",
        f"manifest_{date_str}.json",
    )

    with open(
        output,
        "w",
        encoding="utf8",
    ) as f:

        json.dump(
            manifest,
            f,
            indent=2,
        )


# =============================================================================
# LIVE SCRAPING (requires Telegram auth)
# =============================================================================

async def scrape_channel(client, channel, writer, base_path, date_str,
                         limit=100, message_delay=DEFAULT_MESSAGE_DELAY,
                         channel_delay=DEFAULT_CHANNEL_DELAY, max_retries=3):
    from telethon.tl.types import MessageMediaPhoto
    from telethon.errors import FloodWaitError

    channel_name = channel.strip('@')
    retries = 0

    while True:
        try:
            entity = await client.get_entity(channel)
            channel_title = getattr(
    entity,
    "title",
    channel_name,
)
            messages = []

            channel_image_dir = os.path.join(base_path, "raw", "images", channel_name)
            os.makedirs(channel_image_dir, exist_ok=True)

            logger.info(f"Starting scrape of {channel} (limit={limit})")

            async for message in client.iter_messages(entity, limit=limit):
                image_path: Optional[str] = None
                has_media = message.media is not None

                if has_media and isinstance(message.media, MessageMediaPhoto):
                    filename = f"{message.id}.jpg"
                    image_path = os.path.join(channel_image_dir, filename)
                    try:
                        await client.download_media(message.media, image_path)
                    except Exception as e:
                        logger.warning(f"Failed to download image for message {message.id}: {e}")
                        image_path = None

                message_dict = {
                    "message_id": message.id,
                    "channel_name": channel_name,
                    "channel_title": channel_title,
                    "message_date": message.date.isoformat(),
                    "message_text": message.message or "",
                    "has_media": has_media,
                    "image_path": image_path,
                    "views": message.views or 0,
                    "forwards": message.forwards or 0,
                }

                writer.writerow(list(message_dict.values()))
                messages.append(message_dict)

                if message_delay and message_delay > 0:
                    await asyncio.sleep(message_delay)

            write_channel_messages_json(
                base_path=base_path, date_str=date_str,
                channel_name=channel_name, messages=messages,
            )

            logger.info(f"Finished scraping {channel}: {len(messages)} messages saved")
            if channel_delay and channel_delay > 0:
                await asyncio.sleep(channel_delay)
            return len(messages)

        except FloodWaitError as e:
            wait_seconds = max(int(getattr(e, "seconds", 0) or 0), 1)
            logger.warning(f"FloodWaitError for {channel}: sleeping {wait_seconds}s")
            await asyncio.sleep(wait_seconds)
            retries += 1
            if retries > max_retries:
                logger.error(f"Too many FloodWait retries for {channel}. Skipping.")
                return 0
        except Exception as e:
            logger.error(f"Error scraping {channel}: {e}")
            return 0


async def scrape_all_channels(client, channels, base_path, limit=100,
                              message_delay=DEFAULT_MESSAGE_DELAY,
                              channel_delay=DEFAULT_CHANNEL_DELAY):
    await client.start()
    logger.info(f"Client authenticated. Scraping {len(channels)} channels...")

    csv_dir = os.path.join(base_path, "raw", "csv", TODAY)
    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(os.path.join(base_path, "raw", "telegram_messages", TODAY), exist_ok=True)
    os.makedirs(os.path.join(base_path, "raw", "images"), exist_ok=True)

    csv_file_path = os.path.join(csv_dir, "telegram_data.csv")
    stats = {}

    with open(csv_file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'message_id', 'channel_name', 'channel_title', 'message_date',
            'message_text', 'has_media', 'image_path', 'views', 'forwards'
        ])

        channel_counts = {}
        for channel in channels:
            logger.info(f"Scraping {channel}...")
            count = await scrape_channel(
                client, channel, writer, base_path, TODAY, limit,
                message_delay, channel_delay,
            )
            stats[channel] = count
            channel_counts[channel.strip("@")] = count

        write_manifest(base_path=base_path, date_str=TODAY,
                       channel_message_counts=channel_counts)

    total = sum(stats.values())
    logger.info(f"Scraping complete. Total messages: {total}")
    for ch, count in stats.items():
        logger.info(f"  {ch}: {count} messages")
    return stats



CHANNEL_COLORS = {
    "CheMed": (0,120,210),
    "LobeliaCosmetics": (180,70,130),
    "TikvahPharma": (40,140,90),
}


def _create_placeholder_image(path: str, channel_name: str = "", msg_id: int = 0,
                              text_snippet: str = "") -> None:
    from PIL import Image, ImageDraw, ImageFont

    bg = CHANNEL_COLORS.get(channel_name, (60, 60, 60))
    img = Image.new("RGB", (400, 300), bg)
    draw = ImageDraw.Draw(img)

    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        font_lg = ImageFont.load_default()
        font_sm = font_lg

    draw.text((20, 20), f"@{channel_name}", fill="white", font=font_lg)
    draw.text((20, 55), f"Message #{msg_id}", fill=(200, 200, 200), font=font_sm)

    # Word-wrap the snippet onto the image
    words = text_snippet[:120].split()
    lines, line = [], ""
    for w in words:
        if len(line + " " + w) > 40:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(line)

    y = 100
    for ln in lines[:5]:
        draw.text((20, y), ln, fill=(220, 220, 220), font=font_sm)
        y += 22

    draw.text((20, 270), "DEMO IMAGE", fill=(255, 255, 255, 128), font=font_sm)

    img.save(path, "JPEG", quality=85)


def run_demo(base_path: str, limit: int) -> None:
    logger.info("[DEMO MODE] Generating sample economics/business data")

    date_str = TODAY
    csv_dir = os.path.join(base_path, "raw", "csv", date_str)
    os.makedirs(csv_dir, exist_ok=True)
    csv_file_path = os.path.join(csv_dir, "telegram_data.csv")

    channel_counts = {}
    now = datetime.now(timezone.utc)

    with open(csv_file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "message_id", "channel_name", "channel_title", "message_date",
            "message_text", "has_media", "image_path", "views", "forwards",
        ])

        for channel_name, channel_data in SAMPLE_MESSAGES.items():
            channel_title = channel_data["title"]
            posts = channel_data["posts"][:limit]
            messages = []

            channel_image_dir = os.path.join(base_path, "raw", "images", channel_name)
            os.makedirs(channel_image_dir, exist_ok=True)

            logger.info(f"[DEMO] Scraping @{channel_name} (limit={limit})")

            for i, (text, has_media) in enumerate(posts):
                msg_id = 1000 + i
                msg_date = (now - timedelta(hours=i * 4 + random.randint(0, 3))).isoformat()
                image_path = None

                if has_media:
                    image_path = os.path.join(channel_image_dir, f"{msg_id}.jpg")
                    _create_placeholder_image(image_path, channel_name, msg_id, text)

                views = random.randint(80, 8000)
                forwards = random.randint(0, views // 8)

                msg = {
                    "message_id": msg_id,
                    "channel_name": channel_name,
                    "channel_title": channel_title,
                    "message_date": msg_date,
                    "message_text": text,
                    "has_media": has_media,
                    "image_path": image_path,
                    "views": views,
                    "forwards": forwards,
                }
                messages.append(msg)
                writer.writerow(list(msg.values()))

            write_channel_messages_json(
                base_path=base_path, date_str=date_str,
                channel_name=channel_name, messages=messages,
            )
            channel_counts[channel_name] = len(messages)
            logger.info(f"[DEMO] Finished @{channel_name}: {len(messages)} messages saved")

    write_manifest(base_path=base_path, date_str=date_str,
                   channel_message_counts=channel_counts)

    total = sum(channel_counts.values())
    logger.info(f"[DEMO] Complete. Total messages: {total}")
    for ch, count in channel_counts.items():
        logger.info(f"  @{ch}: {count} messages")
    logger.info(f"[DEMO] Data lake populated at: {base_path}/raw/")
    logger.info(f"[DEMO] Log file: logs/scrape_{date_str}.log")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Telegram Scraper for Ethiopian Business & Economics Channels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python src/scraper.py --demo --path data --limit 20
    python src/scraper.py --path data --limit 500
        """
    )
    parser.add_argument("--path", type=str, default="data")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--message-delay", type=float, default=DEFAULT_MESSAGE_DELAY)
    parser.add_argument("--channel-delay", type=float, default=DEFAULT_CHANNEL_DELAY)
    parser.add_argument("--demo", action="store_true",
                        help="Generate sample data without Telegram auth")
    args = parser.parse_args()

    if args.demo:
        run_demo(args.path, args.limit)
    else:
        if not api_id_str or not api_hash:
            print("ERROR: Missing Tg_API_ID or Tg_API_HASH in .env file")
            sys.exit(1)

        from telethon import TelegramClient
        api_id = int(api_id_str)
        client = TelegramClient("telegram_scraper_session", api_id, api_hash)
        logger.info("Telegram client initialized")

        target_channels = [
            '@CheMed',  
            '@LobeliaCosmetics', 
            '@TikvahPharma',          
        ]

        async def main():
            async with client:
                await scrape_all_channels(
                    client, target_channels, args.path, args.limit,
                    message_delay=args.message_delay, channel_delay=args.channel_delay,
                )

        asyncio.run(main())
