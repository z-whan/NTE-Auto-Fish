import ctypes
import os
import sys
import tkinter as tk
from tkinter import messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

from modules.gui import AutoFishApp


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    executable = sys.executable
    if executable.lower().endswith("python.exe"):
        pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
        if os.path.exists(pythonw):
            executable = pythonw

    params = " ".join(f'"{arg}"' for arg in sys.argv)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        params,
        APP_DIR,
        1,
    )
    return result > 32


def main():
    if not is_admin():
        if relaunch_as_admin():
            return
        messagebox.showerror("需要管理员权限", "请以管理员身份运行程序。")
        return

    root = tk.Tk()
    AutoFishApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
