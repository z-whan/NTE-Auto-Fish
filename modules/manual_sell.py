import os
import time

from modules.controller import Controller
from modules.keyboard import Keyboard
from modules.logger import logger
from modules.settings import AutomationSettings, APP_DIR
from modules.template import Template


SELL_TEMPLATE_DIR = os.path.join(APP_DIR, "assets", "templates", "sell")

MENU_OPEN = Template(os.path.join(SELL_TEMPLATE_DIR, "MENU_OPEN.png"), masked=True)
WAREHOUSE_READY = Template(os.path.join(SELL_TEMPLATE_DIR, "WAREHOUSE_READY.png"), masked=True)
SELL_CONFIRM = Template(os.path.join(SELL_TEMPLATE_DIR, "SELL_CONFIRM.png"), masked=True)
SELL_SUCCESS = Template(os.path.join(SELL_TEMPLATE_DIR, "SELL_SUCCESS.png"), masked=True)


FISH_WAREHOUSE_TAB_POS = (106, 283)
SELL_ALL_POS = (728, 662)
CONFIRM_POS = (792, 476)
SUCCESS_EMPTY_POS = (650, 657)
CLOSE_MENU_POS = (1238, 43)

DEFAULT_SIMILARITY = 0.85
CONFIRM_SIMILARITY = DEFAULT_SIMILARITY
CONFIRM_FRAMES = 3


class ManualSellError(Exception):
    pass


def settle_ui(seconds, reason):
    logger.info(f"[SELL] Waiting {seconds:.2f}s for UI to settle: {reason}.")
    time.sleep(seconds)


def wait_for_template(
    controller,
    template,
    timeout,
    interval=0.2,
    similarity=DEFAULT_SIMILARITY,
    confirm_frames=CONFIRM_FRAMES,
):
    start_time = time.time()
    best_score = 0
    best_pos = None
    matched_frames = 0

    logger.info(
        f"[SELL] Waiting for {template.name} for up to {timeout:.1f}s "
        f"(similarity>={similarity:.2f}, frames={confirm_frames})..."
    )
    for frame in controller.loop(interval=interval):
        elapsed = time.time() - start_time
        score, pos = template.best_match(frame)
        if score > best_score:
            best_score = score
            best_pos = pos

        if score >= similarity:
            matched_frames += 1
            if matched_frames >= confirm_frames:
                logger.info(
                    f"[SELL] Confirmed {template.name}: score={score:.3f}, "
                    f"pos={pos}, frames={matched_frames}."
                )
                return True
        else:
            matched_frames = 0

        if elapsed >= timeout:
            raise ManualSellError(
                f"Timed out waiting for {template.name}. "
                f"Best score={best_score:.3f}, pos={best_pos}."
            )


def run_sell_sequence(controller, keyboard):
    logger.info("[SELL] Focusing game window before sell input.")
    if not controller.focus_window():
        raise ManualSellError("Could not focus game window before pressing Q.")
    settle_ui(0.30, "game window focus")

    logger.info("[SELL] Pressing Q to open Fishing Master menu.")
    keyboard.click("q", duration=0.05)
    settle_ui(0.80, "menu opening after Q")

    wait_for_template(controller, MENU_OPEN, timeout=5, interval=0.2)
    settle_ui(0.30, "menu open confirmed")

    logger.info("[SELL] Clicking fish warehouse tab.")
    controller.mouse_click(FISH_WAREHOUSE_TAB_POS)
    settle_ui(0.60, "warehouse tab click")
    wait_for_template(controller, WAREHOUSE_READY, timeout=5, interval=0.2)
    settle_ui(0.40, "warehouse ready confirmed")

    logger.info("[SELL] Clicking sell all button.")
    controller.mouse_click(SELL_ALL_POS)
    settle_ui(0.60, "sell all click")
    wait_for_template(
        controller,
        SELL_CONFIRM,
        timeout=5,
        interval=0.2,
        similarity=CONFIRM_SIMILARITY,
    )
    settle_ui(0.30, "confirm dialog ready")

    logger.info("[SELL] Clicking confirm button.")
    controller.mouse_click(CONFIRM_POS)
    settle_ui(0.60, "confirm click")
    wait_for_template(controller, SELL_SUCCESS, timeout=8, interval=0.2)
    settle_ui(0.40, "sell success confirmed")

    logger.info("[SELL] Closing sell-success screen.")
    controller.mouse_click(SUCCESS_EMPTY_POS)
    settle_ui(0.50, "success screen close click")
    wait_for_template(controller, WAREHOUSE_READY, timeout=5, interval=0.2)
    settle_ui(0.30, "returned to warehouse")

    logger.info("[SELL] Closing Fishing Master menu.")
    controller.mouse_click(CLOSE_MENU_POS)
    settle_ui(0.50, "menu close click")

    logger.info("[SELL] Fish-selling sequence completed.")
    return True


def run_manual_sell_sequence(settings=None):
    settings = settings or AutomationSettings()
    controller = None

    try:
        logger.info("[SELL] Starting manual fish-selling sequence.")
        logger.info("[SELL] Initializing controller for manual sell.")
        controller = Controller(
            window_name=settings.window_name,
            recovery_timeout=settings.no_recovery_timeout,
        )
        keyboard = Keyboard()
        run_sell_sequence(controller, keyboard)
        logger.info("[SELL] Manual fish-selling sequence completed.")
        return True
    except ManualSellError as e:
        logger.error(f"[SELL] Manual fish-selling workflow failed: {e}")
        return False
    except Exception:
        logger.exception("[SELL] Manual fish-selling workflow crashed.")
        return False
    finally:
        if controller is not None:
            controller.close()
