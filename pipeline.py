"""
Task 5 — Dagster orchestration for the medical Telegram warehouse pipeline.

Launch:
    dagster dev -f pipeline.py
    Open http://localhost:3000
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dagster import (
    DagsterRunStatus,
    Definitions,
    Failure,
    RunStatusSensorContext,
    ScheduleDefinition,
    job,
    op,
    run_status_sensor,
)

PROJECT_ROOT = Path(__file__).resolve().parent


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    context=None,
) -> str:
    log = context.log if context else None
    display = " ".join(cmd)
    if log:
        log.info("Running: %s", display)

    result = subprocess.run(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    if result.stdout and log:
        log.info(result.stdout.strip())
    if result.returncode != 0:
        if log:
            log.error(result.stderr.strip())
        raise Failure(description=f"Command failed ({display}): {result.stderr.strip()}")

    return result.stdout


@op(description="Scrape Telegram channels into the raw data lake.")
def scrape_telegram_data(context) -> str:
    script = PROJECT_ROOT / "src" / "telegram_scraper.py"
    if not script.is_file():
        raise Failure(description=f"Scraper not found: {script}")

    demo = os.getenv("SCRAPER_DEMO", "true").lower() in {"1", "true", "yes"}
    limit = os.getenv("SCRAPER_LIMIT", "100")
    cmd = [sys.executable, str(script), "--path", "data", "--limit", limit]
    if demo:
        cmd.append("--demo")

    run_cmd(cmd, context=context)
    context.log.info("Telegram scrape finished (demo=%s)", demo)
    return "scraped"


@op(description="Load raw JSON and images metadata into PostgreSQL raw schema.")
def load_raw_to_postgres(context, _scrape: str) -> str:
    script = PROJECT_ROOT / "src" / "load_to_postgres.py"
    run_cmd(
        [sys.executable, str(script), "--path", "data"],
        context=context,
    )
    return "loaded"


@op(description="Run dbt staging and mart models.")
def run_dbt_transformations(context, _loaded: str) -> str:
    dbt_dir = PROJECT_ROOT / "medical_warehouse"
    run_cmd(
        ["dbt", "run", "--profiles-dir", "."],
        cwd=dbt_dir,
        context=context,
    )
    return "transformed"


@op(description="Run YOLO detection, load results, and rebuild fct_image_detections.")
def run_yolo_enrichment(context, _transformed: str) -> str:
    detect = PROJECT_ROOT / "src" / "yolo_detect.py"
    loader = PROJECT_ROOT / "src" / "load_yolo_to_postgres.py"
    dbt_dir = PROJECT_ROOT / "medical_warehouse"

    yolo_demo = os.getenv("YOLO_DEMO", "false").lower() in {"1", "true", "yes"}
    detect_cmd = [sys.executable, str(detect)]
    if yolo_demo:
        detect_cmd.append("--demo")

    run_cmd(detect_cmd, context=context)
    run_cmd([sys.executable, str(loader)], context=context)
    run_cmd(
        ["dbt", "run", "--select", "fct_image_detections", "--profiles-dir", "."],
        cwd=dbt_dir,
        context=context,
    )
    return "enriched"


@job(name="medical_warehouse_job", description="End-to-end ELT pipeline for Telegram medical data.")
def medical_warehouse_job():
    scraped = scrape_telegram_data()
    loaded = load_raw_to_postgres(scraped)
    transformed = run_dbt_transformations(loaded)
    run_yolo_enrichment(transformed)


daily_schedule = ScheduleDefinition(
    job=medical_warehouse_job,
    cron_schedule="0 2 * * *",
    name="daily_medical_warehouse_schedule",
    description="Run the full pipeline daily at 02:00 UTC.",
)


@run_status_sensor(
    run_status=DagsterRunStatus.FAILURE,
    name="pipeline_failure_alert",
    minimum_interval_seconds=60,
)
def pipeline_failure_alert(context: RunStatusSensorContext):
    """Log alert on pipeline failure (extend with Slack/email in production)."""
    run = context.dagster_run
    context.log.error(
        "ALERT: Pipeline run %s failed for job %s. Check Dagster UI logs.",
        run.run_id,
        run.job_name,
    )


defs = Definitions(
    jobs=[medical_warehouse_job],
    schedules=[daily_schedule],
    sensors=[pipeline_failure_alert],
)
