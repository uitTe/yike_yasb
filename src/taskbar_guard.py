"""独立监视 Dock 进程并管理系统任务栏。"""

import logging
import sys
from pathlib import Path

from core.utils.single_instance import single_instance_lock
from core.utils.win32.taskbar import watch_taskbars
from settings import DEFAULT_CONFIG_DIRECTORY

if __name__ == "__main__":
    if sys.argv[1] == "--animation":
        from core.utils.win32.window_animation import watch_window_animations

        sys.exit(watch_window_animations(int(sys.argv[2]), sys.argv[3]))
    logging.basicConfig(
        filename=Path(DEFAULT_CONFIG_DIRECTORY) / "taskbar-guard.log",
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    with single_instance_lock("yasb_windows_taskbar"):
        sys.exit(watch_taskbars(int(sys.argv[1]), sys.argv[2]))
