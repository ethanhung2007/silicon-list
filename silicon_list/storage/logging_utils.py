import logging
from pathlib import Path
import sys

def setup_logger(log_file: Path) -> logging.Logger:
    """Configures the root logger to write errors to a file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger("silicon_list")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if setup multiple times
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.WARNING) # Only warning and above to file
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger

def print_summary(new_listings_count: int, tier_counts: dict[int, int], results_file: Path):
    """Prints the exact short summary to stdout."""
    t1 = tier_counts.get(1, 0)
    t2 = tier_counts.get(2, 0)
    t3 = tier_counts.get(3, 0)
    print(f"[Silicon List] Run complete - {new_listings_count} new listings ({t1} Tier 1, {t2} Tier 2, {t3} Tier 3). See {results_file}")
