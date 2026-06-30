"""Task 1 scraper entry point — delegates to telegram_scraper."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("telegram_scraper.py")),
        run_name="__main__",
    )
