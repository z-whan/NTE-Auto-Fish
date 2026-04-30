import time
import ctypes
import sys
import json
import os
from datetime import datetime
from modules.logger import logger

if not ctypes.windll.shell32.IsUserAnAdmin():
    logger.error("This script must be run as administrator.")
    sys.exit(1)

from modules.controller import Controller
from modules.fish_bar import FishBar
from modules.template import *
from modules.keyboard import Keyboard

logger.info("Initializing controllers...")
controller = Controller()
fish_bar = FishBar(controller)
keyboard = Keyboard()
keyboard.start_stop_listener()
logger.info("Initialization complete. Starting main loop.")

SETTLE_SCREEN_TIMEOUT = 20
SETTLE_CLICK_INTERVAL = 0.7
CLICK_BLANK_FAST_TIMEOUT = 0.8
STATS_PATH = os.path.join("logs", "stats.json")

def load_stats():
    if not os.path.exists(STATS_PATH):
        return {"successful_fish": 0, "last_success_at": None}

    try:
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load stats.json; starting from zero.")
        return {"successful_fish": 0, "last_success_at": None}

    stats.setdefault("successful_fish", 0)
    stats.setdefault("last_success_at", None)
    return stats

def save_stats(stats):
    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def record_successful_fish():
    stats = load_stats()
    stats["successful_fish"] += 1
    stats["last_success_at"] = datetime.now().isoformat(timespec="seconds")
    save_stats(stats)
    logger.info(f"Successful fish count: {stats['successful_fish']}")

def wait_until_appear(template, timeout, interval=0.1, post_match_delay=0.1):
    logger.debug(f"Waiting for {template} with timeout {timeout}s...")
    start_time = time.time()
    for frame in controller.loop(interval=interval):
        if template.match(frame):
            logger.debug(f"Found {template}.")
            if post_match_delay > 0:
                controller.sleep(post_match_delay)
            return
        if time.time() - start_time > timeout:
            logger.warning(f"Wait for {template} timeout after {timeout}s.")
            raise TimeoutError(f"Wait for {template} failed after {timeout}s.")

def try_wait_until_appear(template, timeout, interval=0.03, post_match_delay=0):
    logger.debug(f"Quick waiting for {template} with timeout {timeout}s...")
    start_time = time.time()
    for frame in controller.loop(interval=interval):
        if template.match(frame):
            logger.debug(f"Found {template}.")
            if post_match_delay > 0:
                controller.sleep(post_match_delay)
            return True
        if time.time() - start_time > timeout:
            return False

def close_result_screen():
    logger.info("Closing result screen...")
    start_time = time.time()
    last_click_time = 0

    while time.time() - start_time <= SETTLE_SCREEN_TIMEOUT:
        for frame in controller.loop(interval=0.05):
            current_time = time.time()
            if HOOK.match(frame):
                logger.info("Result screen closed; ready for next cast.")
                return True

            if current_time - last_click_time >= SETTLE_CLICK_INTERVAL:
                controller.mouse_click()
                last_click_time = current_time

            if current_time - start_time > SETTLE_SCREEN_TIMEOUT:
                logger.warning("Result screen did not close in time; restarting main loop.")
                return False

stats = load_stats()
save_stats(stats)
logger.info(f"Loaded successful fish count: {stats['successful_fish']}")

while True:
    try:
        wait_until_appear(HOOK, 3)
        logger.info("Spinning rod...")
        keyboard.click('f')

        wait_until_appear(TAKE_BAIT, 10)
        logger.info("Taking bait...")
        keyboard.click('f')
        fish_bar.start()
        record_successful_fish()

        if try_wait_until_appear(CLICK_BLANK, CLICK_BLANK_FAST_TIMEOUT):
            logger.info("Clicking blank after detecting prompt...")
        else:
            logger.info("CLICK_BLANK prompt not detected quickly; clicking blank as fallback...")
        controller.mouse_click()
        close_result_screen()
    except TimeoutError as e:
        controller.mouse_click()
        logger.warning(f"{e} Restarting main loop.")
        continue
