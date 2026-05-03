import json
import os
import time
from dataclasses import dataclass
from datetime import datetime

from modules.controller import Controller, StopRequested
from modules.fish_bar import FishBar
from modules.keyboard import Keyboard
from modules.logger import logger
from modules.manual_sell import ManualSellError, run_sell_sequence
from modules.settings import AutomationSettings
from modules.template import CLICK_BLANK, HOOK


@dataclass
class AutomationRunResult:
    fish_count: int = 0
    golden_fish_count: int = 0
    bait_used_count: int = 0
    sell_count: int = 0


def load_stats(settings):
    default_stats = {
        "successful_fish": 0,
        "golden_fish": 0,
        "last_success_at": None,
        "last_golden_at": None,
    }

    if not os.path.exists(settings.stats_path):
        return default_stats

    try:
        with open(settings.stats_path, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load stats.json; starting from zero.")
        return default_stats

    stats.setdefault("successful_fish", 0)
    stats.setdefault("golden_fish", 0)
    stats.setdefault("last_success_at", None)
    stats.setdefault("last_golden_at", None)
    stats.setdefault("errors", 0)
    stats.setdefault("last_error_at", None)
    stats.setdefault("last_error", None)
    return stats


def save_stats(settings, stats):
    os.makedirs(os.path.dirname(settings.stats_path), exist_ok=True)
    with open(settings.stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def record_successful_fish(settings, is_golden=False, click_blank_wait=None):
    stats = load_stats(settings)
    stats["successful_fish"] += 1
    stats["last_success_at"] = datetime.now().isoformat(timespec="seconds")
    if is_golden:
        stats["golden_fish"] += 1
        stats["last_golden_at"] = stats["last_success_at"]
    save_stats(settings, stats)
    if is_golden:
        logger.info(
            f"Golden fish detected. CLICK_BLANK wait={click_blank_wait:.2f}s, "
            f"golden fish count: {stats['golden_fish']}."
        )
    logger.info(f"Successful fish count: {stats['successful_fish']}")


def record_error(settings, message):
    stats = load_stats(settings)
    stats["errors"] += 1
    stats["last_error_at"] = datetime.now().isoformat(timespec="seconds")
    stats["last_error"] = message
    save_stats(settings, stats)
    logger.error(f"{message} Error count: {stats['errors']}")


def wait_for_hook(controller, settings, timeout=None, allow_timeout_fallback=True):
    timeout = settings.hook_wait_timeout if timeout is None else timeout
    logger.info("Waiting for HOOK prompt...")
    start_time = time.time()
    for frame in controller.loop(interval=settings.template_poll_interval):
        if HOOK.match(frame):
            logger.info("HOOK prompt detected.")
            return True

        if time.time() - start_time >= timeout:
            if allow_timeout_fallback:
                logger.warning(
                    f"HOOK prompt not detected after {timeout}s; "
                    "pressing F anyway because invalid F inputs are filtered by the game."
                )
                return False

            logger.warning(f"HOOK prompt not detected after {timeout}s.")
            return False


def press_f_until_fish_bar(controller, keyboard, fish_bar, settings):
    logger.info("Pressing F until fish bar appears...")
    f_press_interval = 1 / max(settings.f_click_frequency, 0.1)
    last_press_time = 0
    start_time = time.time()
    f_click_count = 0

    for frame in controller.loop(interval=settings.template_poll_interval):
        if fish_bar.is_visible(frame):
            elapsed = time.time() - start_time
            logger.info(f"Fish bar appeared. F clicked {f_click_count} times over {elapsed:.2f}s.")
            return True

        if time.time() - start_time >= settings.no_recovery_timeout:
            record_error(
                settings,
                f"Fish bar did not appear after {settings.no_recovery_timeout:.0f}s. "
                "Stopping this run."
            )
            return False

        current_time = time.time()
        if current_time - last_press_time >= f_press_interval:
            keyboard.click("f", duration=settings.f_press_duration)
            f_click_count += 1
            last_press_time = current_time


def click_game_window(controller, reason):
    logger.info(f"Mouse click in game window: {reason}")
    controller.mouse_click()


def wait_for_click_blank_then_click(controller, settings):
    logger.info(f"Waiting for CLICK_BLANK prompt for up to {settings.click_blank_timeout}s...")
    start_time = time.time()
    matched_frames = 0
    best_score = 0
    best_pos = None

    for frame in controller.loop(interval=settings.template_poll_interval):
        elapsed = time.time() - start_time
        score, pos = CLICK_BLANK.best_match(frame)
        if score > best_score:
            best_score = score
            best_pos = pos

        if elapsed >= settings.click_blank_min_wait and score >= settings.click_blank_similarity:
            matched_frames += 1
        else:
            matched_frames = 0

        if matched_frames >= settings.click_blank_confirm_frames:
            confirmed_wait = time.time() - start_time
            logger.info(
                f"CLICK_BLANK prompt confirmed. Clicking game window. "
                f"score={score:.3f}, pos={pos}, frames={matched_frames}, "
                f"wait={confirmed_wait:.2f}s."
            )
            click_game_window(controller, "CLICK_BLANK confirmed")
            return confirmed_wait

        if elapsed >= settings.click_blank_timeout:
            message = "CLICK_BLANK prompt timeout. Clicking game window and restarting."
            logger.warning(f"Best CLICK_BLANK match before timeout: score={best_score:.3f}, pos={best_pos}.")
            click_game_window(controller, "CLICK_BLANK timeout fallback")
            record_error(settings, message)
            return None


def run_autofish(
    stop_event,
    settings=None,
    on_bait_used=None,
    on_fish_caught=None,
    on_frame=None,
    on_auto_sell_remaining=None,
):
    settings = settings or AutomationSettings()
    run_result = AutomationRunResult()
    controller = None
    auto_sell_limit = None
    auto_sell_remaining = None
    pending_auto_sell = False

    def sync_auto_sell_config():
        nonlocal auto_sell_limit, auto_sell_remaining, pending_auto_sell
        configured_limit = settings.auto_sell_after_bait_count
        if configured_limit == auto_sell_limit:
            return

        auto_sell_limit = configured_limit
        pending_auto_sell = False
        if auto_sell_limit is None:
            auto_sell_remaining = None
            logger.info("[SELL] Auto sell by bait count disabled.")
        else:
            auto_sell_remaining = auto_sell_limit
            logger.info(f"[SELL] Auto sell enabled: sell after {auto_sell_limit} bait uses.")

        if on_auto_sell_remaining is not None:
            on_auto_sell_remaining(auto_sell_remaining)

    def mark_bait_used_for_auto_sell():
        nonlocal auto_sell_remaining, pending_auto_sell
        sync_auto_sell_config()
        if auto_sell_limit is None:
            return

        auto_sell_remaining = max(0, auto_sell_remaining - 1)
        logger.info(
            f"[SELL] Auto sell countdown: remaining bait uses before sell={auto_sell_remaining}."
        )
        if on_auto_sell_remaining is not None:
            on_auto_sell_remaining(auto_sell_remaining)

        if auto_sell_remaining == 0:
            pending_auto_sell = True
            logger.info("[SELL] Auto sell scheduled after the current fishing cycle completes.")

    def run_pending_auto_sell_if_needed():
        nonlocal auto_sell_remaining, pending_auto_sell
        sync_auto_sell_config()
        if not pending_auto_sell:
            return True

        logger.info("[SELL] Auto sell pending. Waiting for HOOK prompt before opening menu.")
        if not wait_for_hook(
            controller,
            settings,
            timeout=settings.no_recovery_timeout,
            allow_timeout_fallback=False,
        ):
            record_error(
                settings,
                "[SELL] HOOK prompt was not detected before auto sell. Stopping this run."
            )
            return False

        logger.info("[SELL] Starting auto fish-selling sequence.")
        try:
            run_sell_sequence(controller, keyboard)
        except StopRequested:
            raise
        except ManualSellError as e:
            record_error(settings, f"[SELL] Auto fish-selling workflow failed: {e} Stopping this run.")
            return False
        except Exception:
            logger.exception("[SELL] Auto fish-selling workflow crashed.")
            record_error(settings, "[SELL] Auto fish-selling workflow crashed. Stopping this run.")
            return False

        run_result.sell_count += 1
        pending_auto_sell = False
        if auto_sell_limit is not None:
            auto_sell_remaining = auto_sell_limit
            if on_auto_sell_remaining is not None:
                on_auto_sell_remaining(auto_sell_remaining)
        logger.info("[SELL] Auto fish-selling sequence completed; countdown reset.")
        return True

    try:
        logger.info("Initializing controllers...")
        controller = Controller(
            window_name=settings.window_name,
            stop_event=stop_event,
            recovery_timeout=settings.no_recovery_timeout,
            on_screenshot=on_frame,
        )
        fish_bar = FishBar(controller)
        keyboard = Keyboard()
        logger.info("Initialization complete. Waiting for fishing prompts.")

        stats = load_stats(settings)
        save_stats(settings, stats)
        logger.info(f"Loaded successful fish count: {stats['successful_fish']}")
        sync_auto_sell_config()

        while not stop_event.is_set():
            try:
                if not run_pending_auto_sell_if_needed():
                    break

                wait_for_hook(controller, settings)
                if not press_f_until_fish_bar(controller, keyboard, fish_bar, settings):
                    break
                run_result.bait_used_count += 1
                if on_bait_used is not None:
                    on_bait_used(1)
                mark_bait_used_for_auto_sell()
                fish_bar.start()
                click_blank_wait = wait_for_click_blank_then_click(controller, settings)
                if click_blank_wait is not None:
                    is_golden = click_blank_wait >= settings.golden_fish_wait_threshold
                    record_successful_fish(settings, is_golden, click_blank_wait)
                    run_result.fish_count += 1
                    if is_golden:
                        run_result.golden_fish_count += 1
                    if on_fish_caught is not None:
                        on_fish_caught(1, 1 if is_golden else 0)
            except TimeoutError as e:
                if stop_event.is_set():
                    break
                record_error(settings, f"{e} Stopping this run.")
                break
    except StopRequested:
        logger.info("Automation stopped.")
    except TimeoutError as e:
        record_error(settings, f"{e} Stopping this run.")
    except Exception:
        logger.exception("Automation crashed.")
        raise
    finally:
        if controller is not None:
            controller.close()
    return run_result
