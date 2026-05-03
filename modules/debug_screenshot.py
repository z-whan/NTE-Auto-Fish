import os
from datetime import datetime

import cv2

from modules.controller import Controller
from modules.logger import logger
from modules.settings import APP_DIR, AutomationSettings

DEBUG_SCREENSHOT_DIR = os.path.join(APP_DIR, "debug_screenshots")


def save_debug_screenshot(frame, save_dir=DEBUG_SCREENSHOT_DIR):
    if frame is None:
        raise ValueError("No game window frame is available to save.")

    os.makedirs(save_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = os.path.join(save_dir, f"debug_capture_{timestamp}.png")

    if not cv2.imwrite(path, frame):
        raise OSError(f"Failed to write screenshot to {path}")

    logger.info(f"Debug screenshot saved: {path}")
    return path


def capture_debug_screenshot(settings=None):
    settings = settings or AutomationSettings()
    controller = None
    try:
        controller = Controller(
            window_name=settings.window_name,
            recovery_timeout=settings.no_recovery_timeout,
        )
        frame = controller.screenshot()
        return save_debug_screenshot(frame)
    finally:
        if controller is not None:
            controller.close()
