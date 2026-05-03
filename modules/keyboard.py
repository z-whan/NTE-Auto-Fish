import ctypes
import time
import threading
import os
from modules.logger import logger

# 硬件扫描码表 (Scan Codes)
SCAN_CODES = {
    'a': 0x1E,
    'd': 0x20,
    'f': 0x21,
    'q': 0x10,
    'w': 0x11,
    's': 0x1F,
    'esc': 0x01,
}

SendInput = ctypes.windll.user32.SendInput

# C struct definitions for SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", Input_I)]

def press_key(key):
    if key not in SCAN_CODES:
        return
    hex_code = SCAN_CODES[key]
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hex_code, 0x0008, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def release_key(key):
    if key not in SCAN_CODES:
        return
    hex_code = SCAN_CODES[key]
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hex_code, 0x0008 | 0x0002, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

class Keyboard:
    @staticmethod
    def press(key):
        press_key(key)

    @staticmethod
    def release(key):
        release_key(key)

    @staticmethod
    def click(key, duration=0.1):
        press_key(key)
        time.sleep(duration)
        release_key(key)

    @staticmethod
    def start_stop_listener():
        """
        Starts a background thread to listen for emergency stop hotkeys.
        When pressed, the entire process will be terminated.
        """
        def listen():
            stop_hotkeys = {
                0xC0: "`/·",
                0x7B: "F12",
            }
            logger.info("Emergency stop hotkeys: `/· or F12.")
            while True:
                for vk_code, label in stop_hotkeys.items():
                    if ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000:
                        logger.warning(f"Emergency stop hotkey {label} detected. Terminating...")
                        os._exit(0)
                time.sleep(0.05)

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
