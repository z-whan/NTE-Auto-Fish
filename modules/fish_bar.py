import numpy as np
import cv2
import time

from modules.controller import Controller, StopRequested
from modules.keyboard import Keyboard
from modules.logger import logger

class FishBar:
    RECT = (403, 60, 495, 40)   # (x, y, w, h)
    GREEN_BAR = (173, 202, 42)  # BGR range
    YELLOW_CURSOR = (157, 246, 254) # BGR

    def __init__(self, controller: Controller):
        self.controller = controller
        self.keyboard = Keyboard()
        self.current_key = None
    
    def _get_green_bar(self, screenshot):
        x, y, w, h = self.RECT
        roi = screenshot[y:y+h, x:x+w]
        
        target = np.array(self.GREEN_BAR, dtype=np.int16)
        dist = np.sum(np.abs(roi.astype(np.int16) - target), axis=2)
        
        threshold = 10
        mask = dist < threshold
        cols = np.where(np.any(mask, axis=0))[0]
        if cols.size > 0:
            left, right = cols[0] + x, cols[-1] + x
            width = right - left
            return (int(left + width * 0.4), int(left + width * 0.6))
        return None

    def _get_yellow_cursor(self, screenshot):
        x, y, w, h = self.RECT
        roi = screenshot[y:y+h, x:x+w]
        
        target = np.array(self.YELLOW_CURSOR, dtype=np.int16)
        dist = np.sum(np.abs(roi.astype(np.int16) - target), axis=2)
        
        threshold = 10 
        mask = dist < threshold
        cols = np.where(np.any(mask, axis=0))[0]
        if cols.size > 0:
            return int((cols[0] + cols[-1]) // 2 + x)
        return None

    def _press(self, key):
        if self.current_key == key:
            return
        
        self._release_all()
        if key:
            logger.debug(f"Pressing '{key}'")
            self.keyboard.press(key)
            self.current_key = key

    def _release_all(self):
        if self.current_key:
            logger.debug(f"Releasing '{self.current_key}'")
            self.keyboard.release(self.current_key)
            self.current_key = None

    def wait_until_ui_appear(self, timeout=8):
        logger.debug("Waiting for fish bar UI to appear...")
        start_time = time.time()
        for frame in self.controller.loop():
            if self._get_green_bar(frame) is not None and self._get_yellow_cursor(frame) is not None:
                logger.debug("Fish bar UI appeared.")
                return
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Wait for fish bar UI failed after {timeout}s.")

    def start(self):
        logger.info("Starting fishing...")
        try:
            self.wait_until_ui_appear()

            missing_green_bar_count = 0
            for frame in self.controller.loop(interval=0):
                green_bar = self._get_green_bar(frame)

                if green_bar is None:
                    missing_green_bar_count += 1
                    if missing_green_bar_count > 10: # 连续 10 帧检测不到绿条才认为结束
                        logger.info("Fishing ended.")
                        break
                    continue

                missing_green_bar_count = 0
                left, right = green_bar
                cursor = self._get_yellow_cursor(frame)

                if cursor is None:
                    continue

                if cursor < left:
                    self._press('d')
                elif cursor > right:
                    self._press('a')
                else:
                    self._release_all()
        except StopRequested:
            logger.info("Fishing stopped.")
            raise
        finally:
            self._release_all()
            

        
