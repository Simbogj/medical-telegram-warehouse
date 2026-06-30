"""
Task 3 — YOLOv8 object detection on scraped Telegram images.

Scans data/raw/images/{channel_name}/{message_id}.jpg, runs YOLOv8n,
classifies each image, and writes results to CSV for warehouse loading.

Usage:
    python src/yolo_detect.py
    python src/yolo_detect.py --image-dir data/raw/images --output data/yolo_results.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from pathlib import Path

from ultralytics import YOLO

logger = logging.getLogger("yolo_detect")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# COCO classes commonly associated with product/container imagery
PRODUCT_CLASSES = {
    "bottle",
    "cup",
    "bowl",
    "wine glass",
    "vase",
    "book",
    "handbag",
    "suitcase",
    "backpack",
    "cell phone",
    "laptop",
    "remote",
    "toothbrush",
}


def get_image_paths(root_dir: Path) -> list[Path]:
    return sorted(
        p for p in root_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def parse_image_metadata(image_path: Path) -> tuple[int | None, str | None]:
    """Extract message_id and channel_name from data/raw/images/{channel}/{id}.jpg."""
    channel_name = image_path.parent.name
    try:
        message_id = int(image_path.stem)
    except ValueError:
        message_id = None
    return message_id, channel_name


def extract_class_names(result) -> list[str]:
    if result.boxes is None or len(result.boxes) == 0:
        return []
    names = []
    for cls_id in result.boxes.cls.cpu().numpy().astype(int):
        names.append(result.names[int(cls_id)])
    return names


def categorize_image(class_names: list[str]) -> tuple[str, str]:
    """
    Return (detected_class, image_category).

    Categories:
      promotional     — person + product-like object
      product_display — product-like object, no person
      lifestyle       — person, no product
      other           — neither
    """
    if not class_names:
        return "none", "other"

    has_person = "person" in class_names
    has_product = any(name in PRODUCT_CLASSES for name in class_names)
    detected_class = class_names[0]

    if has_person and has_product:
        return detected_class, "promotional"
    if has_product and not has_person:
        return detected_class, "product_display"
    if has_person and not has_product:
        return detected_class, "lifestyle"
    return detected_class, "other"


def run_demo_detection(image_dir: str, output_csv: str) -> int:
    """Assign image categories without YOLO (CI/demo fallback)."""
    img_root = Path(image_dir)
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not img_root.exists():
        logger.warning("Image directory does not exist: %s", img_root)
        return 0

    image_paths = get_image_paths(img_root)
    demo_categories = ["product_display", "promotional", "product_display", "lifestyle", "other"]

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "image_path", "message_id", "channel_name",
                "detected_class", "confidence_score", "image_category",
            ],
        )
        writer.writeheader()
        for idx, img_path in enumerate(image_paths):
            message_id, channel_name = parse_image_metadata(img_path)
            category = demo_categories[idx % len(demo_categories)]
            writer.writerow({
                "image_path": str(img_path).replace("\\", "/"),
                "message_id": message_id if message_id is not None else "",
                "channel_name": channel_name or "",
                "detected_class": "demo",
                "confidence_score": "0.7500",
                "image_category": category,
            })

    logger.info("Demo YOLO CSV written: %d images → %s", len(image_paths), output_path)
    return len(image_paths)


def run_detection(
    image_dir: str,
    output_csv: str,
    model_path: str = "yolov8n.pt",
) -> int:
    img_root = Path(image_dir)
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not img_root.exists():
        logger.warning("Image directory does not exist: %s", img_root)
        output_path.write_text(
            "image_path,message_id,channel_name,detected_class,confidence_score,image_category\n",
            encoding="utf-8",
        )
        return 0

    image_paths = get_image_paths(img_root)
    if not image_paths:
        logger.warning("No images found under %s", img_root)
        return 0

    model = YOLO(model_path)
    rows_written = 0

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "image_path",
                "message_id",
                "channel_name",
                "detected_class",
                "confidence_score",
                "image_category",
            ],
        )
        writer.writeheader()

        for img_path in image_paths:
            message_id, channel_name = parse_image_metadata(img_path)
            results = model(str(img_path), verbose=False)
            result = results[0]
            class_names = extract_class_names(result)
            detected_class, image_category = categorize_image(class_names)

            if result.boxes is not None and len(result.boxes) > 0:
                avg_conf = float(result.boxes.conf.cpu().numpy().mean())
            else:
                avg_conf = 0.0

            writer.writerow({
                "image_path": str(img_path).replace("\\", "/"),
                "message_id": message_id if message_id is not None else "",
                "channel_name": channel_name or "",
                "detected_class": detected_class,
                "confidence_score": f"{avg_conf:.4f}",
                "image_category": image_category,
            })
            rows_written += 1

    logger.info("YOLO detection complete: %d images → %s", rows_written, output_path)
    return rows_written


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run YOLOv8 detection on scraped images")
    parser.add_argument(
        "--image-dir",
        default=os.getenv("RAW_IMAGE_DIR", "data/raw/images"),
    )
    parser.add_argument(
        "--output",
        default=os.getenv("YOLO_OUTPUT_CSV", "data/yolo_results.csv"),
    )
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Write heuristic categories without running YOLO (CI/offline fallback)",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo_detection(args.image_dir, args.output)
    else:
        run_detection(args.image_dir, args.output, args.model)


if __name__ == "__main__":
    main()
