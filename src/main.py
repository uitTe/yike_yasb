import asyncio
import logging
import os
import signal
import sys
from sys import argv
from types import FrameType, TracebackType

import qasync  # pyright: ignore[reportMissingTypeStubs]

from core.application import YASBApplication
from core.bar_manager import BarManager
from core.config import get_config_and_stylesheet
from core.events.service import EventService
from core.log import enable_debug_logging, init_logger
from core.tray import SystemTrayManager
from core.utils.controller import start_cli_server
from core.utils.process import start_independent_process
from core.utils.single_instance import single_instance_lock
from core.utils.system_colors import SystemColorsService
from core.utils.win32.bindings.user32 import GetShellWindow, get_window_thread_process_id
from core.watcher import create_observer
from env import load_env, set_font_engine
from settings import IS_FROZEN


def main():
    """Main entry point"""
    app = YASBApplication(argv)

    loop = qasync.QEventLoop(app)
    try:
        loop.run_until_complete(main_async(app))  # pyright: ignore[reportUnknownMemberType]
    finally:
        loop.close()


async def main_async(app: YASBApplication):
    """
    Async entry point
    Required for qasync to work properly
    """
    # Event to signal application shutdown
    app_close_event = asyncio.Event()

    # Assign the loop and close event to the app instance
    # This allows the controller to close the app gracefully from another thread
    app.loop = asyncio.get_running_loop()
    app.close_event = app_close_event

    # Prevent the app from exiting when closing the dialogs
    app.setQuitOnLastWindowClosed(False)

    # Connect the app's aboutToQuit signal to the close event
    app.aboutToQuit.connect(app_close_event.set)

    def handle_sigint(_signum: int, _frame: FrameType | None) -> None:
        logging.info("KeyboardInterrupt (Ctrl+C) detected. Initiating graceful shutdown...")
        app_close_event.set()

    try:
        signal.signal(signal.SIGINT, handle_sigint)
    except ValueError:
        pass

    # Initialize configuration early after the single instance check
    config, stylesheet = get_config_and_stylesheet()

    if config.debug:
        enable_debug_logging()
        logging.info("Debug mode enabled.")

    # Initialise bars and background event listeners
    manager = BarManager(config, stylesheet)

    try:
        manager.initialize_bars(init=True)
        # Initialise file watcher if needed
        observer = create_observer(manager) if config.watch_config or config.watch_stylesheet else None
        if observer:
            observer.start()

        def stop_observer():
            if observer:
                observer.stop()
                observer.join()

        app.aboutToQuit.connect(stop_observer)

        # Initialize system colors service
        if config.system_colors:
            SystemColorsService.start_service()

        # Build system tray icon
        if config.show_systray:
            tray_manager = SystemTrayManager(manager)
            tray_manager.show()

        await app_close_event.wait()
    finally:
        # Cancel async tasks while loop is still running
        current = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        app.quit()


if __name__ == "__main__":
    init_logger()
    load_env()
    set_font_engine()

    def exception_hook(_exctype: type, value: BaseException, _traceback: TracebackType | None):
        EventService().clear()
        logging.error("Unhandled exception", exc_info=value)
        sys.exit(1)

    sys.excepthook = exception_hook

    try:
        if IS_FROZEN:
            _, shell_pid = get_window_thread_process_id(GetShellWindow())
            if os.getppid() != shell_pid:
                pid = start_independent_process([sys.executable, *sys.argv[1:]])
                logging.info("YASB 已启动独立运行实例，进程编号：%s", pid)
                sys.exit(0)

        # Acquire the single instance lock before doing any heavy initialization
        with single_instance_lock():
            start_cli_server()
            main()
    except Exception:
        logging.exception("Exception during application startup")
        sys.exit(1)
