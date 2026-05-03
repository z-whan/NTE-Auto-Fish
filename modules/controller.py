import bettercam
import win32api
import win32gui
import win32con
import time
import random
from modules.logger import logger

class StopRequested(Exception):
    pass

class Controller:
    def __init__(self, window_name='异环  ', stop_event=None, recovery_timeout=60, on_screenshot=None):
        self.camera = bettercam.create(output_color="BGR")
        self.camera.start(target_fps=120, video_mode=True)
        self.window_name = window_name
        self.stop_event = stop_event
        self.recovery_timeout = recovery_timeout
        self.on_screenshot = on_screenshot
        self.last_check_time = 0
        self.last_error_log_time = 0
        self.last_error_message = None
        self.suppressed_error_count = 0
        self.loop_error_started_at = None
        self.rect = None
        try:
            self._ensure_hwnd()
            self._bring_to_top(force_topmost=True)
        except Exception:
            self.close()
            raise

    def _stop_requested(self):
        return self.stop_event is not None and self.stop_event.is_set()

    def _ensure_hwnd(self):
        start_time = time.time()
        logged_waiting = False
        while True:
            if self._stop_requested():
                raise StopRequested("Stop requested while waiting for game window.")
            self.hwnd = win32gui.FindWindow(None, self.window_name)
            if self.hwnd:
                logger.debug(f"Found window '{self.window_name}' with hwnd {self.hwnd}.")
                break
            else:
                if not logged_waiting:
                    logger.warning(
                        f"Window '{self.window_name}' not found. "
                        f"Waiting up to {self.recovery_timeout:.0f}s before stopping this run."
                    )
                    logged_waiting = True
                if time.time() - start_time >= self.recovery_timeout:
                    raise TimeoutError(f"Window '{self.window_name}' not found after {self.recovery_timeout:.0f}s.")
                time.sleep(1)

    def _log_error_throttled(self, message, interval=5):
        current_time = time.time()
        if message != self.last_error_message:
            self.last_error_message = message
            self.last_error_log_time = current_time
            self.suppressed_error_count = 0
            logger.warning(message)
            return

        self.suppressed_error_count += 1
        if current_time - self.last_error_log_time >= interval:
            logger.warning(f"{message} (suppressed {self.suppressed_error_count} repeats)")
            self.last_error_log_time = current_time
            self.suppressed_error_count = 0

    def _try_foreground(self):
        if win32gui.GetForegroundWindow() == self.hwnd:
            self._bring_to_top()
            return True

        try:
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.hwnd)
            self._bring_to_top()
            time.sleep(0.2)
            return True
        except Exception as e:
            self._log_error_throttled(f"Could not set game window foreground: {e}")
            self._bring_to_top(force_topmost=True)
            return False

    def _bring_to_top(self, force_topmost=False):
        try:
            flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            if force_topmost:
                win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
                win32gui.SetWindowPos(self.hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            else:
                win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOP, 0, 0, 0, 0, flags)
        except Exception as e:
            self._log_error_throttled(f"Could not bring game window to top: {e}")

    def focus_window(self):
        if not win32gui.IsWindow(self.hwnd):
            self._ensure_hwnd()

        focused = self._try_foreground()
        if focused:
            logger.info(f"Game window focused: '{self.window_name}'.")
        return focused

    def screenshot(self):
        current_time = time.time()
        
        # Limit expensive win32gui calls to every 0.5s for extreme speed
        if current_time - self.last_check_time > 0.5 or self.rect is None:
            if not win32gui.IsWindow(self.hwnd):
                self._ensure_hwnd()

            self._try_foreground()

            rect = win32gui.GetWindowRect(self.hwnd)
            left, top, right, bottom = rect
            w, h = right - left, bottom - top
            
            screen_w = self.camera.width
            screen_h = self.camera.height

            is_out_of_screen = (left < 0 or top < 0 or right > screen_w or bottom > screen_h)

            if is_out_of_screen:
                self._log_error_throttled(
                    f"Game window is partially outside the capture area (rect: {rect}); "
                    "keeping its current position."
                )

            self.rect = rect
            self.last_check_time = time.time()

        # Fetch frame from background thread instead of blocking synchronous grab
        frame = self.camera.get_latest_frame()
        if frame is None:
            frame = self.camera.grab()
            if frame is None:
                return None
                
        left, top, right, bottom = self.rect
        screen_h, screen_w = frame.shape[:2]
        
        # Ensure crop bounds are valid
        left = max(0, min(left, screen_w))
        right = max(0, min(right, screen_w))
        top = max(0, min(top, screen_h))
        bottom = max(0, min(bottom, screen_h))

        cropped = frame[top:bottom, left:right]
        if cropped.shape[1] < 1290 or cropped.shape[1] > 1310:
            self._log_error_throttled(
                f"Unexpected game window capture size: {cropped.shape[1]}x{cropped.shape[0]}. "
                "Expected about 1300px wide for 1280x720; continuing anyway."
            )
        if self.on_screenshot is not None:
            try:
                self.on_screenshot(cropped)
            except Exception as e:
                self._log_error_throttled(f"Debug screenshot frame callback failed: {e}")
        return cropped

    def loop(self, interval=0.1):
        while not self._stop_requested():
            try:
                s = self.screenshot()
            except ValueError:
                raise
            except TimeoutError:
                raise
            except StopRequested:
                raise
            except Exception as e:
                if self.loop_error_started_at is None:
                    self.loop_error_started_at = time.time()
                self._log_error_throttled(f"Error during screenshot: {e}")
                if time.time() - self.loop_error_started_at >= self.recovery_timeout:
                    raise TimeoutError(
                        f"Screenshot failed for {self.recovery_timeout:.0f}s; stopping this run."
                    )
            else:
                if s is not None:
                    self.loop_error_started_at = None
                    yield s
            time.sleep(interval)
        raise StopRequested("Stop requested.")

    def mouse_click(self, pos=(650, 700)):
        if not win32gui.IsWindow(self.hwnd):
            self._ensure_hwnd()

        self._try_foreground()

        x, y = win32gui.ClientToScreen(self.hwnd, pos)
        logger.debug(f"Mouse click at client pos {pos} (screen pos {x}, {y}).")
        win32api.SetCursorPos((x, y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def sleep(self, seconds, variance=0.2):
        low = seconds * (1 - variance)
        high = seconds * (1 + variance)
        t = sum(random.uniform(low, high) for _ in range(3)) / 3
        logger.debug(f"Sleeping for {t:.3f}s (target: {seconds}s).")
        end_time = time.time() + t
        while time.time() < end_time:
            if self._stop_requested():
                raise StopRequested("Stop requested during sleep.")
            time.sleep(min(0.05, end_time - time.time()))

    def close(self):
        try:
            self.camera.stop()
        except Exception:
            pass
