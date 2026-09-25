import fastf1
from fastf1.ergast import Ergast
from fastf1.exceptions import RateLimitExceededError

import requests
import asyncio
import schedule
import json
import os
import logging
import warnings
import functools
from time import sleep
from tqdm import tqdm
from datetime import datetime, timedelta

# Suppress FastF1 warnings and logger so it doesn't mess up our tqdm progress bar
warnings.filterwarnings("ignore", category=UserWarning, module="fastf1")
logging.getLogger("fastf1").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CACHE_DIR = os.path.join(BASE_DIR, 'cache', 'standings')
FASTF1_CACHE_DIR = os.path.join(BASE_DIR, 'cache', 'fastf1')

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(FASTF1_CACHE_DIR, exist_ok=True)

fastf1.Cache.enable_cache(FASTF1_CACHE_DIR)

def retry_on_rate_limit(max_retries=6, base_sleep=1.0):
    """Decorator to automatically retry API calls when rate limited (429/Too Many Requests)"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for retry in range(max_retries):
                try:
                    sleep(base_sleep)
                    result = func(*args, **kwargs)
                    # Special check: FastF1 sometimes returns empty DataFrames on 429 instead of raising
                    if hasattr(result, 'empty') and getattr(result, 'empty'):
                        raise Exception("429 Too Many Requests - Empty DataFrame returned")
                    return result
                except Exception as e:
                    if '429' in str(e) or 'Too Many Requests' in str(e) or 'Empty DataFrame' in str(e):
                        sleep_time = 2 ** retry
                        logger.warning(f"Rate limit in {func.__name__} (Attempt {retry+1}/{max_retries}). Retrying in {sleep_time}s...")
                        sleep(sleep_time)
                    else:
                        raise e
            raise Exception(f"Rate limit exceeded persistently in {func.__name__}")
        return wrapper
    return decorator


@retry_on_rate_limit()
def fetch_schedule(year: int):
    return fastf1.get_event_schedule(year)

@retry_on_rate_limit()
def fetch_standings(ergast: Ergast, year: int, round_num: int):
    return ergast.get_driver_standings(year, round_num)


def update_year_standings(year: int, all_driver_standings: dict, all_constructor_standings: dict) -> tuple[list[dict], list[dict]]:
    """Fetches and caches the driver and constructor standings for a given year"""

    logger.info(f"Starting to update standings for year {year}")
    ergast = Ergast()
    
    driver_evolution = []
    constructor_evolution = []

    try:
        schedule = fetch_schedule(year)
        total_rounds = schedule['RoundNumber'].max()
    except Exception as e:
        logger.error(f"Failed to fetch schedule for year {year}: {e}")
        return driver_evolution, constructor_evolution

    for round_num in tqdm(range(1, total_rounds + 1), leave=False, desc=f"Updating standings for {year}"):

        # Check if standings for this round are already cached
        is_cached_driver = any(r.get('round') == str(round_num) for r in all_driver_standings.get(str(year), []))
        is_cached_constructor = any(r.get('round') == str(round_num) for r in all_constructor_standings.get(str(year), []))
        
        if is_cached_driver and is_cached_constructor:
            # Reconstruct evolution from cache directly
            cached_d = next((r for r in all_driver_standings[str(year)] if r.get('round') == str(round_num)), None)
            cached_c = next((r for r in all_constructor_standings[str(year)] if r.get('round') == str(round_num)), None)
            if cached_d and cached_c:
                driver_evolution.append(cached_d)
                constructor_evolution.append(cached_c)
            continue

        round_data_driver = {"round": str(round_num)}
        round_data_constructor = {"round": str(round_num)}

        # Fetch standings
        try: 
            driver_res = fetch_standings(ergast, year, round_num)
            
            if driver_res.content and not driver_res.content[0].empty:
                driver_df = driver_res.content[0]

                for _, row in driver_df.iterrows():
                    code = row.get('driverCode')
                    if not code or str(code) == 'nan':
                        code = str(row.get('familyName', 'UNK'))[:3].upper()
                    round_data_driver[str(code)] = float(row['points'])

                    # Constructor standings
                    constructor_code = str(row['constructorIds'][-1])
                    if constructor_code not in round_data_constructor:
                        round_data_constructor[constructor_code] = float(row['points'])
                    else:
                        round_data_constructor[constructor_code] += float(row['points'])
                    
                driver_evolution.append(round_data_driver)
                constructor_evolution.append(round_data_constructor)
                
        except Exception as e:
            logger.error(f"Failed to fetch year {year} round {round_num} standings: {e}")
            raise
            
    return driver_evolution, constructor_evolution

def update_all_standings() -> None:
    """Updates the standings for all years from 1950 to the current year"""

    driver_cache_file = os.path.join(CACHE_DIR, 'driver_standings.json')
    constructor_cache_file = os.path.join(CACHE_DIR, 'constructor_standings.json')

    if os.path.exists(driver_cache_file):
        with open(driver_cache_file, 'r') as f:
            all_driver_standings = json.load(f)
    else:
        all_driver_standings = {}

    if os.path.exists(constructor_cache_file):
        with open(constructor_cache_file, 'r') as f:
            all_constructor_standings = json.load(f)
    else:
        all_constructor_standings = {}

    current_year = datetime.now().year
    for year in tqdm(range(1950, current_year + 1), desc="Updating standings for all years"):

        # Skip if the data for this year is already fully cached (and not the current year)
        if str(year) in all_driver_standings and str(year) in all_constructor_standings and year != current_year:
            continue

        # 10 Retries with delay in case of API issues or rate limits
        for _ in range(10):
            try:
                driver_evolution, constructor_evolution = update_year_standings(year, all_driver_standings, all_constructor_standings)
                break
            except RateLimitExceededError as e:
                logger.warning(f"Rate limit hit while updating standings for year {year}: {e}. Retrying after delay.")
                sleep(3610)  # Wait before retrying
            except Exception as e:
                logger.error(f"Error updating standings for year {year}: {e}")
                sleep(60)  # Wait before retrying

        if driver_evolution and constructor_evolution:
            all_driver_standings[str(year)] = driver_evolution
            all_constructor_standings[str(year)] = constructor_evolution

            # Sort dictionaries by year keys
            all_driver_standings = {k: all_driver_standings[k] for k in sorted(all_driver_standings.keys(), key=int)}
            all_constructor_standings = {k: all_constructor_standings[k] for k in sorted(all_constructor_standings.keys(), key=int)}

            with open(os.path.join(CACHE_DIR, 'driver_standings.json'), 'w') as f:
                json.dump(all_driver_standings, f, indent=4)
            with open(os.path.join(CACHE_DIR, 'constructor_standings.json'), 'w') as f:
                json.dump(all_constructor_standings, f, indent=4)

    # Always ensure the final saved JSON files are cleanly sorted, even if we skipped fetching
    all_driver_standings = {k: all_driver_standings[k] for k in sorted(all_driver_standings.keys(), key=int)}
    all_constructor_standings = {k: all_constructor_standings[k] for k in sorted(all_constructor_standings.keys(), key=int)}
    
    with open(os.path.join(CACHE_DIR, 'driver_standings.json'), 'w') as f:
        json.dump(all_driver_standings, f, indent=4)
    with open(os.path.join(CACHE_DIR, 'constructor_standings.json'), 'w') as f:
        json.dump(all_constructor_standings, f, indent=4)

async def daily_updater():
    """Schedules the update of standings to run daily at midnight"""
    schedule.every().day.at("00:00").do(update_all_standings)
    
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)  # Check every minute for pending tasks


if __name__ == "__main__":
    # 為了不干擾終端機的進度條 (tqdm)，我們將 log 輸出到 updater.log 檔案中
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("updater.log", encoding='utf-8')
        ]
    )
    
    update_all_standings()