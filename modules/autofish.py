import json
import os
import time
from datetime import datetime

from modules.controller import Controller, StopRequested
from modules.fish_bar import FishBar
from modules.keyboard import Keyboard
from modules.logger import logger
from modules.settings import AutomationSettings
from modules.template import CLICK_BLANK, HOOK, TAKE_BAIT


def load_stats(settings):
    if not os.path.exists(settings.stats_path):
        return {"successful_fish": 0, "last_success_at": None}

    try:
        with open(settings.stats_path, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load stats.json; starting from zero.")
        return {"successful_fish": 0, "last_success_at": None}

    stats.setdefault("successful_fish", 0)
    stats.setdefault("last_success_at", None)
    return stats


def save_stats(settings, stats):
    os.makedirs(os.path.dirname(settings.stats_path), exist_ok=True)
    with open(settings.stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def record_successful_fish(settings):
    stats = load_stats(settings)
    stats["successful_fish"] += 1
    stats["last_success_at"] = datetime.now().isoformat(timespec="seconds")
    save_stats(settings, stats)
    logger.info(f"Successful fish count: {stats['successful_fish']}")


def wait_until_appear(controller, template, timeout, interval=0.1, post_match_delay=0.1):
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


def try_wait_until_appear(controller, template, timeout, interval=0.03, post_match_delay=0):
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
    return False


def close_result_screen(controller, settings):
    logger.info("Closing result screen...")
    start_time = time.time()
    last_click_time = 0

    while time.time() - start_time <= settings.settle_screen_timeout:
        for frame in controller.loop(interval=0.05):
            current_time = time.time()
            if HOOK.match(frame):
                logger.info("Result screen closed; ready for next cast.")
                return True

            if current_time - last_click_time >= settings.settle_click_interval:
                controller.mouse_click()
                last_click_time = current_time

            if current_time - start_time > settings.settle_screen_timeout:
                logger.warning("Result screen did not close in time; restarting main loop.")
                return False
    return False


def run_autofish(stop_event, settings=None):
    settings = settings or AutomationSettings()
    controller = None
    try:
        logger.info("Initializing controllers...")
        controller = Controller(window_name=settings.window_name, stop_event=stop_event)
        fish_bar = FishBar(controller)
        keyboard = Keyboard()
        logger.info("Initialization complete. Waiting for fishing prompts.")

        stats = load_stats(settings)
        save_stats(settings, stats)
        logger.info(f"Loaded successful fish count: {stats['successful_fish']}")

        while not stop_event.is_set():
            try:
                wait_until_appear(controller, HOOK, 3)
                logger.info("Spinning rod...")
                keyboard.click("f")

                wait_until_appear(controller, TAKE_BAIT, 10)
                logger.info("Taking bait...")
                keyboard.click("f")
                fish_bar.start()
                record_successful_fish(settings)

                if try_wait_until_appear(controller, CLICK_BLANK, settings.click_blank_fast_timeout):
                    logger.info("Clicking blank after detecting prompt...")
                else:
                    logger.info("CLICK_BLANK prompt not detected quickly; clicking blank as fallback...")
                controller.mouse_click()
                close_result_screen(controller, settings)
            except TimeoutError as e:
                if stop_event.is_set():
                    break
                controller.mouse_click()
                logger.warning(f"{e} Restarting main loop.")
    except StopRequested:
        logger.info("Automation stopped.")
    except Exception:
        logger.exception("Automation crashed.")
        raise
    finally:
        if controller is not None:
            controller.close()
