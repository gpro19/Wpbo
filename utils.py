from datetime import datetime, timedelta
import time
from database import DatabaseManager

def scheduled_reset():
    """Task terjadwal untuk reset quota harian"""
    db = DatabaseManager()
    while True:
        now = datetime.now()
        # Reset setiap hari jam 00:00 WIB (GMT+7) atau jam 17:00 UTC
        next_reset = (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_reset - now).total_seconds()
        
        logger.info(f"Sleeping for {sleep_seconds} seconds until next reset...")
        time.sleep(sleep_seconds)
        
        db.reset_daily_quota()
        logger.info("Daily quota reset completed")
