import os
from dataclasses import dataclass

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class AutomationSettings:
    window_name: str = "异环  "
    settle_screen_timeout: float = 20
    settle_click_interval: float = 0.7
    click_blank_fast_timeout: float = 0.8
    stats_path: str = os.path.join(APP_DIR, "logs", "stats.json")
