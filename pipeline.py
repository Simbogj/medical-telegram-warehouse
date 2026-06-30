import os
import subprocess
from pathlib import Path

from dagster import op, job, ScheduleDefinition, Definitions, get_dagster_logger

# Helper to run a shell command and raise on failure
def run_cmd(cmd: list[str], env: dict | None = None):
    logger = get_dagster_logger()
    logger.info(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result.stdout

# -------------------------------------------------------------------
# Ops
# -------------------------------------------------------------------
@op(description="Scrape Telegram channels and store raw JSON/files in the data lake.")
def scrape_telegram_data(context):
    # Assume a script src/telegram_scraper.py exists with a main entrypoint
    script_path = Path(__file__).parent / "src" / "telegram_scraper.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"Telegram scraper script not found at {script_path}")
    run_cmd(["python", str(script_path)])
    context.log.info("Telegram scraping completed.")

@op(description="Load the raw JSON files produced by the scraper into the PostgreSQL raw schema.")
def load_raw_to_postgres(context):
    script_path = Path(__file__).parent / "src" / "load_to_postgres.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"Raw‑to‑Postgres loader not found at {script_path}")
    run_cmd(["python", str(script_path)])
    context.log.info("Raw data loaded into PostgreSQL.")

@op(description="Execute dbt models to transform raw data into the star schema.")
def run_dbt_transformations(context):
    # dbt project lives in medical_warehouse/ – we run `dbt run`
    cwd = Path(__file__).parent / "medical_warehouse"
    run_cmd(["dbt", "run"], env=os.environ.copy())
    context.log.info("dbt transformations executed.")

@op(description="Run YOLO object detection on downloaded images and load results.")
def run_yolo_enrichment(context):
    # First run detection script
    detect_script = Path(__file__).parent / "src" / "yolo_detect.py"
    if not detect_script.is_file():
        raise FileNotFoundError(f"YOLO detection script not found at {detect_script}")
    run_cmd(["python", str(detect_script)])
    # Then load CSV into PostgreSQL
    load_script = Path(__file__).parent / "src" / "load_yolo_to_postgres.py"
    if not load_script.is_file():
        raise FileNotFoundError(f"YOLO loader script not found at {load_script}")
    run_cmd(["python", str(load_script)])
    context.log.info("YOLO enrichment completed and data loaded.")

# -------------------------------------------------------------------
# Job definition – defines execution order
# -------------------------------------------------------------------
@job(name="medical_warehouse_job")
def medical_warehouse_job():
    # Define dependencies
    raw = scrape_telegram_data()
    loaded = load_raw_to_postgres.after(raw)()
    transformed = run_dbt_transformations.after(loaded)()
    enriched = run_yolo_enrichment.after(transformed)()
    return enriched

# -------------------------------------------------------------------
# Schedule – daily run at 02:00 UTC (adjustable)
# -------------------------------------------------------------------
daily_schedule = ScheduleDefinition(
    job=medical_warehouse_job,
    cron_schedule="0 2 * * *",  # 02:00 UTC each day
    name="daily_medical_warehouse_schedule",
)

# Export definitions for Dagster UI
Definitions(jobs=[medical_warehouse_job], schedules=[daily_schedule])
