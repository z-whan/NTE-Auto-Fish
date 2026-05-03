import ctypes
import logging
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext, ttk

from modules.autofish import load_stats, run_autofish
from modules.debug_screenshot import capture_debug_screenshot, save_debug_screenshot
from modules.logger import logger
from modules.manual_sell import run_manual_sell_sequence
from modules.settings import AutomationSettings

TOGGLE_HOTKEY_LABEL = "` / ·"
VK_TOGGLE = 0xC0
VK_EXIT = 0x7B


class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            self.log_queue.put(self.format(record))
        except Exception:
            pass


class AutoFishApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NTE AutoFish")
        self.root.geometry("900x560")
        self.root.minsize(720, 420)

        self.stop_event = threading.Event()
        self.worker = None
        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.hotkey_stop = threading.Event()
        self.exiting = False
        self.current_settings = AutomationSettings()
        self.app_started_at = datetime.now()
        self.last_ended_at = None
        self.app_fish_count = 0
        self.app_golden_fish_count = 0
        self.current_bait_count = None
        self.auto_sell_after_count = None
        self.auto_sell_remaining_count = None
        self.f_click_frequency = self.current_settings.f_click_frequency
        self.f_click_frequency_var = tk.StringVar(value=self._format_frequency(self.f_click_frequency))
        self.latest_frame = None
        self.latest_frame_lock = threading.Lock()
        self.debug_screenshot_worker = None
        self.manual_sell_worker = None
        self.debug_window = None
        self.debug_screenshot_button = None
        self.manual_sell_button = None

        self._build_ui()
        self._refresh_stats_table()
        self._attach_logger()
        self._bind_shortcuts()
        self._start_hotkey_listener()

        logger.info("GUI ready. Shortcuts: `/· toggle start/stop, F12 exit.")
        self.root.after(80, self._poll_queues)
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        header = ttk.Frame(self.root, padding=(14, 12, 14, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="NTE AutoFish 控制台", font=("Microsoft YaHei UI", 15, "bold"))
        title.grid(row=0, column=0, sticky="w")

        self.status_var = tk.StringVar(value="已就绪")
        status = ttk.Label(header, textvariable=self.status_var)
        status.grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = ttk.Frame(header)
        actions.grid(row=0, column=1, rowspan=2, sticky="e")

        self.toggle_button = ttk.Button(actions, text=f"开始运行  {TOGGLE_HOTKEY_LABEL}", command=self.toggle)
        self.toggle_button.grid(row=0, column=0, padx=(0, 8))

        debug_button = ttk.Button(actions, text="调试", command=self.open_debug_window)
        debug_button.grid(row=0, column=1, padx=(0, 8))

        exit_button = ttk.Button(actions, text="退出  F12", command=self.exit_app)
        exit_button.grid(row=0, column=2)

        bait_frame = ttk.LabelFrame(self.root, text="鱼饵", padding=(14, 8, 14, 10))
        bait_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        self.bait_input_var = tk.StringVar()
        self.bait_display_var = tk.StringVar(value="未启用")
        ttk.Label(bait_frame, text="当前鱼饵数").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.bait_entry = ttk.Entry(bait_frame, textvariable=self.bait_input_var, width=10)
        self.bait_entry.grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Button(bait_frame, text="确认", command=self.confirm_bait_count).grid(row=0, column=2, sticky="w", padx=(0, 16))
        ttk.Label(bait_frame, text="已记录").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Label(bait_frame, textvariable=self.bait_display_var, width=12).grid(row=0, column=4, sticky="w")

        self.auto_sell_after_input_var = tk.StringVar()
        self.auto_sell_remaining_var = tk.StringVar(value="未启用")
        ttk.Label(bait_frame, text="钓鱼").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.auto_sell_after_entry = ttk.Entry(bait_frame, textvariable=self.auto_sell_after_input_var, width=10)
        self.auto_sell_after_entry.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Label(bait_frame, text="次后卖鱼").grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Button(bait_frame, text="确认", command=self.confirm_auto_sell_count).grid(
            row=1, column=3, sticky="w", padx=(0, 16), pady=(8, 0)
        )
        ttk.Label(bait_frame, text="剩余").grid(row=1, column=4, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Label(bait_frame, textvariable=self.auto_sell_remaining_var, width=12).grid(
            row=1, column=5, sticky="w", pady=(8, 0)
        )

        stats_frame = ttk.LabelFrame(self.root, text="统计", padding=(14, 8, 14, 10))
        stats_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))

        self.app_start_var = tk.StringVar()
        self.last_end_var = tk.StringVar()
        self.app_fish_var = tk.StringVar()
        self.app_golden_var = tk.StringVar()
        self.total_fish_var = tk.StringVar()
        self.total_golden_var = tk.StringVar()

        stats_items = [
            ("程序打开时间", self.app_start_var),
            ("最近结束时间", self.last_end_var),
            ("本次打开钓鱼数", self.app_fish_var),
            ("本次打开金色鱼", self.app_golden_var),
            ("程序总计钓鱼数", self.total_fish_var),
            ("程序总计金色鱼", self.total_golden_var),
        ]
        for index, (label, variable) in enumerate(stats_items):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(stats_frame, text=label).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=3)
            ttk.Label(stats_frame, textvariable=variable, width=18).grid(row=row, column=col + 1, sticky="w", padx=(0, 24), pady=3)

        log_frame = ttk.Frame(self.root, padding=(14, 4, 14, 14))
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        shortcut = ttk.Label(
            log_frame,
            text=f"快捷操作：{TOGGLE_HOTKEY_LABEL} 开始/结束运行 / F12 退出程序",
            foreground="#4b5563",
        )
        shortcut.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            height=18,
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")

    def _attach_logger(self):
        handler = QueueLogHandler(self.log_queue)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        self.gui_log_handler = handler

    def _bind_shortcuts(self):
        self.root.bind("<grave>", lambda _event: self.toggle())
        self.root.bind("<F12>", lambda _event: self.exit_app())

    def _start_hotkey_listener(self):
        def listen():
            pressed = set()
            hotkeys = {
                VK_TOGGLE: self.toggle,
                VK_EXIT: self.exit_app,
            }
            while not self.hotkey_stop.is_set():
                for vk_code, action in hotkeys.items():
                    is_down = bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
                    if is_down and vk_code not in pressed:
                        pressed.add(vk_code)
                        self.root.after(0, action)
                    elif not is_down and vk_code in pressed:
                        pressed.remove(vk_code)
                time.sleep(0.05)

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()

    def _format_frequency(self, frequency):
        return f"{frequency:.2f}"

    def _configure_debug_button(self, name, **options):
        button = getattr(self, name, None)
        if button is not None and button.winfo_exists():
            button.configure(**options)

    def open_debug_window(self):
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.lift()
            self.debug_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.debug_window = window
        window.title("调试")
        window.resizable(False, False)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_debug_window)

        content = ttk.Frame(window, padding=(14, 12, 14, 14))
        content.grid(row=0, column=0, sticky="nsew")

        actions = ttk.LabelFrame(content, text="功能", padding=(12, 8, 12, 10))
        actions.grid(row=0, column=0, sticky="ew")

        self.debug_screenshot_button = ttk.Button(actions, text="截图", command=self.capture_debug_screenshot)
        self.debug_screenshot_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.manual_sell_button = ttk.Button(actions, text="卖鱼", command=self.sell_fish_now)
        self.manual_sell_button.grid(row=0, column=1, sticky="ew")
        if self.worker and self.worker.is_alive():
            self.manual_sell_button.configure(state="disabled")

        settings = ttk.LabelFrame(content, text="设置", padding=(12, 8, 12, 10))
        settings.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        ttk.Label(settings, text="F 点击频率").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(settings, textvariable=self.f_click_frequency_var, width=10).grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Label(settings, text="次/秒").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Button(settings, text="确认", command=self.confirm_f_click_frequency).grid(row=0, column=3, sticky="w")

        window.focus_force()

    def _close_debug_window(self):
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.destroy()
        self.debug_window = None
        self.debug_screenshot_button = None
        self.manual_sell_button = None

    def toggle(self):
        if self.worker and self.worker.is_alive():
            self.stop()
        else:
            self.start()

    def start(self):
        if self.worker and self.worker.is_alive():
            logger.info("Automation is already running.")
            return

        self.current_settings = AutomationSettings(
            f_click_frequency=self.f_click_frequency,
            auto_sell_after_bait_count=self.auto_sell_after_count,
        )
        if self.auto_sell_after_count is not None:
            self.auto_sell_remaining_count = self.auto_sell_after_count
            self.auto_sell_remaining_var.set(str(self.auto_sell_remaining_count))
        self.stop_event.clear()
        self.worker = threading.Thread(target=self._worker_main, daemon=True)
        self.worker.start()
        self.status_var.set("运行中")
        self.toggle_button.configure(text=f"结束运行  {TOGGLE_HOTKEY_LABEL}")
        self._configure_debug_button("manual_sell_button", state="disabled")
        logger.info(
            f"Automation start requested. F click frequency: "
            f"{self.current_settings.f_click_frequency:.2f}/s."
        )

    def stop(self):
        if not self.worker or not self.worker.is_alive():
            logger.info("Automation is not running.")
            return

        self.stop_event.set()
        self.status_var.set("正在停止...")
        self.toggle_button.configure(state="disabled")
        logger.info("Automation stop requested.")

    def exit_app(self):
        if self.exiting and self.worker and self.worker.is_alive():
            self.root.after(150, self.exit_app)
            return

        self.exiting = True
        self.hotkey_stop.set()
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            logger.info("Stopping automation before exit...")
            self.root.after(150, self.exit_app)
            return

        logger.removeHandler(self.gui_log_handler)
        self.root.destroy()

    def _worker_main(self):
        try:
            run_result = run_autofish(
                self.stop_event,
                settings=self.current_settings,
                on_bait_used=self._queue_bait_used,
                on_fish_caught=self._queue_fish_caught,
                on_frame=self._remember_latest_frame,
                on_auto_sell_remaining=self._queue_auto_sell_remaining,
            )
        except Exception:
            self.ui_queue.put(("failed", None))
        else:
            self.ui_queue.put(("stopped", run_result))

    def _queue_bait_used(self, count):
        self.ui_queue.put(("bait_used", count))

    def _queue_fish_caught(self, fish_count, golden_fish_count):
        self.ui_queue.put(("fish_caught", (fish_count, golden_fish_count)))

    def _queue_auto_sell_remaining(self, remaining):
        self.ui_queue.put(("auto_sell_remaining", remaining))

    def _remember_latest_frame(self, frame):
        with self.latest_frame_lock:
            self.latest_frame = frame.copy()

    def capture_debug_screenshot(self):
        if self.debug_screenshot_worker and self.debug_screenshot_worker.is_alive():
            logger.info("Debug screenshot is already in progress.")
            return

        self._configure_debug_button("debug_screenshot_button", state="disabled")
        logger.info("Capturing debug screenshot...")
        self.debug_screenshot_worker = threading.Thread(target=self._capture_debug_screenshot_worker, daemon=True)
        self.debug_screenshot_worker.start()

    def _capture_debug_screenshot_worker(self):
        try:
            with self.latest_frame_lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()

            if frame is not None:
                path = save_debug_screenshot(frame)
            else:
                path = capture_debug_screenshot(self.current_settings)

            self.ui_queue.put(("debug_screenshot_saved", path))
        except Exception as e:
            logger.exception("Debug screenshot failed.")
            self.ui_queue.put(("debug_screenshot_failed", str(e)))

    def sell_fish_now(self):
        if self.worker and self.worker.is_alive():
            logger.info("[SELL] Manual fish-selling is disabled while automation is running.")
            return

        if self.manual_sell_worker and self.manual_sell_worker.is_alive():
            logger.info("[SELL] Manual fish-selling workflow is already running.")
            return

        self._configure_debug_button("manual_sell_button", state="disabled")
        self.status_var.set("正在卖鱼...")
        self.manual_sell_worker = threading.Thread(target=self._manual_sell_worker_main, daemon=True)
        self.manual_sell_worker.start()

    def _manual_sell_worker_main(self):
        try:
            success = run_manual_sell_sequence(settings=self.current_settings)
        except Exception:
            logger.exception("[SELL] Unexpected manual sell worker error.")
            self.ui_queue.put(("manual_sell_failed", None))
            return

        if success:
            self.ui_queue.put(("manual_sell_completed", None))
        else:
            self.ui_queue.put(("manual_sell_failed", None))

    def _poll_queues(self):
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(message)

        while True:
            try:
                event, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if event == "bait_used":
                self._consume_bait(payload)
            elif event == "fish_caught":
                fish_count, golden_fish_count = payload
                self.app_fish_count += fish_count
                self.app_golden_fish_count += golden_fish_count
                self._refresh_stats_table()
            elif event == "auto_sell_remaining":
                self._set_auto_sell_remaining(payload)
            elif event == "failed":
                self.last_ended_at = datetime.now()
                self._refresh_stats_table()
                self.status_var.set("运行出错，查看日志")
                self.toggle_button.configure(text=f"开始运行  {TOGGLE_HOTKEY_LABEL}", state="normal")
                self._configure_debug_button("manual_sell_button", state="normal")
            elif event == "debug_screenshot_saved":
                self.status_var.set("截图已保存")
                self._configure_debug_button("debug_screenshot_button", state="normal")
            elif event == "debug_screenshot_failed":
                self.status_var.set("截图失败，查看日志")
                self._configure_debug_button("debug_screenshot_button", state="normal")
            elif event == "manual_sell_completed":
                self.status_var.set("卖鱼完成")
                self._configure_debug_button("manual_sell_button", state="normal")
            elif event == "manual_sell_failed":
                self.status_var.set("卖鱼失败，查看日志")
                self._configure_debug_button("manual_sell_button", state="normal")
            elif event == "stopped":
                self.last_ended_at = datetime.now()
                if payload is not None:
                    logger.info(
                        f"Run summary: fish={payload.fish_count}, "
                        f"golden_fish={payload.golden_fish_count}, "
                        f"bait_used={payload.bait_used_count}, "
                        f"sell={payload.sell_count}."
                    )
                self._refresh_stats_table()
                self.status_var.set("已停止")
                self.toggle_button.configure(text=f"开始运行  {TOGGLE_HOTKEY_LABEL}", state="normal")
                self._configure_debug_button("manual_sell_button", state="normal")

        self.root.after(80, self._poll_queues)

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def confirm_bait_count(self):
        value = self.bait_input_var.get().strip()
        if not value:
            self.current_bait_count = None
            self.bait_display_var.set("未启用")
            logger.info("Bait tracking disabled.")
            return

        try:
            bait_count = int(value)
        except ValueError:
            logger.error("当前鱼饵数必须是整数。")
            self.status_var.set("鱼饵数无效")
            return

        if bait_count < 0:
            logger.error("当前鱼饵数不能小于 0。")
            self.status_var.set("鱼饵数无效")
            return

        self.current_bait_count = bait_count
        self.bait_display_var.set(str(self.current_bait_count))
        logger.info(f"Bait count confirmed: {self.current_bait_count}.")

    def confirm_auto_sell_count(self):
        value = self.auto_sell_after_input_var.get().strip()
        if not value:
            self.auto_sell_after_count = None
            self.auto_sell_remaining_count = None
            self.current_settings.auto_sell_after_bait_count = None
            self.auto_sell_remaining_var.set("未启用")
            logger.info("[SELL] Auto sell by bait count disabled.")
            return

        try:
            auto_sell_after_count = int(value)
        except ValueError:
            logger.error("钓鱼多少次后卖鱼必须是整数。")
            self.status_var.set("卖鱼次数无效")
            return

        if auto_sell_after_count <= 0:
            logger.error("钓鱼多少次后卖鱼必须大于 0。")
            self.status_var.set("卖鱼次数无效")
            return

        self.auto_sell_after_count = auto_sell_after_count
        self.auto_sell_remaining_count = auto_sell_after_count
        self.current_settings.auto_sell_after_bait_count = auto_sell_after_count
        self.auto_sell_remaining_var.set(str(self.auto_sell_remaining_count))
        logger.info(f"[SELL] Auto sell confirmed: sell after {self.auto_sell_after_count} bait uses.")

    def confirm_f_click_frequency(self):
        value = self.f_click_frequency_var.get().strip()
        try:
            frequency = float(value)
        except ValueError:
            logger.error("F 点击频率必须是数字。")
            self.status_var.set("F 点击频率无效")
            return

        if frequency <= 0:
            logger.error("F 点击频率必须大于 0。")
            self.status_var.set("F 点击频率无效")
            return

        self.f_click_frequency = frequency
        self.current_settings.f_click_frequency = frequency
        self.f_click_frequency_var.set(self._format_frequency(frequency))
        self.status_var.set("F 点击频率已更新")
        logger.info(f"F click frequency updated: {frequency:.2f}/s.")

    def _consume_bait(self, bait_used_count):
        if self.current_bait_count is None or bait_used_count <= 0:
            return

        self.current_bait_count = max(0, self.current_bait_count - bait_used_count)
        self.bait_display_var.set(str(self.current_bait_count))
        logger.info(f"Bait count updated: -{bait_used_count}, remaining={self.current_bait_count}.")

    def _set_auto_sell_remaining(self, remaining):
        self.auto_sell_remaining_count = remaining
        if remaining is None:
            self.auto_sell_remaining_var.set("未启用")
        else:
            self.auto_sell_remaining_var.set(str(remaining))

    def _refresh_stats_table(self):
        stats = load_stats(self.current_settings)
        self.app_start_var.set(self.app_started_at.strftime("%Y-%m-%d %H:%M:%S"))
        self.last_end_var.set(
            self.last_ended_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_ended_at else "-"
        )
        self.app_fish_var.set(str(self.app_fish_count))
        self.app_golden_var.set(str(self.app_golden_fish_count))
        self.total_fish_var.set(str(stats.get("successful_fish", 0)))
        self.total_golden_var.set(str(stats.get("golden_fish", 0)))
