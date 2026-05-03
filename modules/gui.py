import ctypes
import logging
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext, ttk

from modules.autofish import load_stats, run_autofish
from modules.logger import logger
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

        exit_button = ttk.Button(actions, text="退出  F12", command=self.exit_app)
        exit_button.grid(row=0, column=1)

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

    def toggle(self):
        if self.worker and self.worker.is_alive():
            self.stop()
        else:
            self.start()

    def start(self):
        if self.worker and self.worker.is_alive():
            logger.info("Automation is already running.")
            return

        self.current_settings = AutomationSettings()
        self.stop_event.clear()
        self.worker = threading.Thread(target=self._worker_main, daemon=True)
        self.worker.start()
        self.status_var.set("运行中")
        self.toggle_button.configure(text=f"结束运行  {TOGGLE_HOTKEY_LABEL}")
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
            )
        except Exception:
            self.ui_queue.put(("failed", None))
        else:
            self.ui_queue.put(("stopped", run_result))

    def _queue_bait_used(self, count):
        self.ui_queue.put(("bait_used", count))

    def _queue_fish_caught(self, fish_count, golden_fish_count):
        self.ui_queue.put(("fish_caught", (fish_count, golden_fish_count)))

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
            elif event == "failed":
                self.last_ended_at = datetime.now()
                self._refresh_stats_table()
                self.status_var.set("运行出错，查看日志")
                self.toggle_button.configure(text=f"开始运行  {TOGGLE_HOTKEY_LABEL}", state="normal")
            elif event == "stopped":
                self.last_ended_at = datetime.now()
                if payload is not None:
                    logger.info(
                        f"Run summary: fish={payload.fish_count}, "
                        f"golden_fish={payload.golden_fish_count}, "
                        f"bait_used={payload.bait_used_count}."
                    )
                self._refresh_stats_table()
                self.status_var.set("已停止")
                self.toggle_button.configure(text=f"开始运行  {TOGGLE_HOTKEY_LABEL}", state="normal")

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

    def _consume_bait(self, bait_used_count):
        if self.current_bait_count is None or bait_used_count <= 0:
            return

        self.current_bait_count = max(0, self.current_bait_count - bait_used_count)
        self.bait_display_var.set(str(self.current_bait_count))
        logger.info(f"Bait count updated: -{bait_used_count}, remaining={self.current_bait_count}.")

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
