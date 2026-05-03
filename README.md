# NTE AutoFish

基于 OpenCV 图像识别的异环自动钓鱼工具。项目当前提供可视化控制台，支持管理员权限启动、开始/结束运行、实时日志显示和基础统计记录。

## 功能

- 可视化窗口控制自动钓鱼流程
- 窗口内实时显示本次打开后的运行日志，并支持上下滚动
- ` / ·` 一键开始或结束运行
- `F12` 退出程序
- 自动记录成功钓鱼次数到本地 `logs/stats.json`
- 启动时自动请求管理员权限

## 运行环境

- Windows
- Python 3.14
- 游戏分辨率建议设置为 `1280x720`

## 安装

```powershell
cd NTE_AutoFish
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## 使用

推荐双击 `run_gui.vbs` 启动，通常不会显示额外的 cmd 窗口。也可以使用 `run.bat` 作为兼容启动方式。

启动后：

- 按 ` / ·` 或点击界面按钮：开始/结束运行
- 按 `F12` 或点击退出按钮：退出程序

## 项目结构

```text
NTE_AutoFish/
  main.py                # 轻量启动入口和管理员权限处理
  modules/
    gui.py               # Tkinter 可视化控制台
    autofish.py          # 自动钓鱼主流程
    controller.py        # 截图、窗口聚焦、鼠标控制
    fish_bar.py          # 钓鱼条识别和按键控制
    keyboard.py          # 键盘输入封装
    logger.py            # 日志配置
    template.py          # 模板识别
  assets/templates/      # 识别模板
  logs/                  # 本地日志和统计文件，默认不提交
```

## 后续方向

此项目会逐步扩展为可视化配置中心，计划把窗口名、快捷键、模板阈值、点击位置、等待超时、钓鱼策略等参数放入界面中管理，实现更高自定义度的钓鱼脚本。

## 注意

本项目仅供学习和技术交流使用。请自行承担使用脚本带来的风险。
