import os
from dataclasses import dataclass

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class AutomationSettings:
    window_name: str = "异环  "
    settle_screen_timeout: float = 20
    settle_click_interval: float = 0.7
    click_blank_fast_timeout: float = 0.8
    click_blank_timeout: float = 10
    click_blank_similarity: float = 0.84
    click_blank_confirm_frames: int = 4
    click_blank_min_wait: float = 1.2
    golden_fish_wait_threshold: float = 4.5
    hook_wait_timeout: float = 3
    f_click_frequency: float = 1 / 0.6
    f_press_duration: float = 0.05
    template_poll_interval: float = 0.05
    no_recovery_timeout: float = 60
    stats_path: str = os.path.join(APP_DIR, "logs", "stats.json")
