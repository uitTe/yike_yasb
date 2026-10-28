"""
YASB CLI

NOTE: Avoid importing heavy libraries directly to avoid slowing down the startup time.

To check the startup time, use the following commands (from venv):
python -X importtime src/cli.py 2> import_times.log
pip install tuna
tuna import_times.log
"""

import argparse
import datetime
import os
import subprocess
import sys
import textwrap
import time
import winreg
from typing import Any

from core.cli.pipe import CLI_SERVER_PIPE_NAME, LOG_SERVER_PIPE_NAME, read_message, write_message
from core.utils.process import is_process_running
from core.utils.win32.bindings.advapi32 import get_current_user_sid
from core.utils.win32.bindings.kernel32 import CloseHandle, CreateFile, GetLastError, ReadFile, WriteFile
from core.utils.win32.bindings.ole32 import create_dispatch
from core.utils.win32.bindings.shell32 import IsUserAnAdmin
from core.utils.win32.constants import (
    GENERIC_READ,
    GENERIC_WRITE,
    INVALID_HANDLE_VALUE,
    MINIDUMP_WITH_DATA_SEGS,
    MINIDUMP_WITH_FULL_MEMORY_INFO,
    MINIDUMP_WITH_HANDLE_DATA,
    MINIDUMP_WITH_INDIRECTLY_REFERENCED_MEMORY,
    MINIDUMP_WITH_PROCESS_THREAD_DATA,
    MINIDUMP_WITH_THREAD_INFO,
    MINIDUMP_WITH_UNLOADED_MODULES,
    OPEN_EXISTING,
)
from core.utils.win32.registry_keys import RUN_KEY, WER_LOCAL_DUMPS_KEY
from settings import APP_NAME, BUILD_VERSION, CLI_VERSION, DEFAULT_CONFIG_DIRECTORY, RELEASE_CHANNEL, SCRIPT_PATH

YASB_VERSION = BUILD_VERSION
YASB_CLI_VERSION = CLI_VERSION
YASB_RELEASE_CHANNEL = RELEASE_CHANNEL

EXE_PATH = os.path.join(SCRIPT_PATH, "yasb.exe")
AUTOSTART_FILE = EXE_PATH if os.path.exists(EXE_PATH) else None


class Format:
    reset = "\033[0m"
    green = "\033[92m"
    yellow = "\033[93m"
    red = "\033[91m"
    red_bg = "\033[41m"
    gray = "\033[90m"
    blue = "\033[94m"
    cyan = "\033[96m"
    magenta = "\033[95m"
    underline = "\033[4m"


class CustomArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("suggest_on_error", True)
        super().__init__(*args, **kwargs)

    def error(self, message: str):
        print(f"\n{Format.red}Error:{Format.reset} {message}\n")
        sys.exit(2)


class CLIHandler:
    """Handles the command-line interface for the application."""

    def __init__(self):
        self.task_handler = CLITaskHandler()
        self.crash_dump_handler = CLICrashDumpHandler()

    def send_command_to_application(self, command: str):
        """
        Send a command to the running YASB application through the pipe.

        Commands can be:
        - "stop" - Stop the application
        - "reload" - Reload the application
        - "show-bar [screen]" - Show the bar on a specific screen
        - "hide-bar [screen]" - Hide the bar on a specific screen
        - "toggle-bar [screen]" - Toggle the bar on a specific screen

        Args:
            command: The command to send
        """
        try:
            pipe_handle = CreateFile(
                CLI_SERVER_PIPE_NAME,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if pipe_handle == INVALID_HANDLE_VALUE:
                print("Failed to connect to YASB. Pipe not found. It may not be running.")
                return

            # Send the command as bytes
            command_bytes = command.encode("utf-8")
            success = WriteFile(pipe_handle, command_bytes)
            if not success:
                print(f"Failed to write command. Err: {GetLastError()}")
                CloseHandle(pipe_handle)
                return

            success, response = ReadFile(pipe_handle, 64 * 1024)
            if not success or len(response) == 0:
                print(f"Failed to read response. Err: {GetLastError()}")
                CloseHandle(pipe_handle)
                return

            response_text = response.decode("utf-8").strip()
            if response_text != "ACK":
                print(f"Received unexpected response: {response_text}")

            CloseHandle(pipe_handle)
        except Exception as e:
            print(f"Error: {e}")

    def _open_startup_registry(self, access_flag: int):
        """Helper function to open the startup registry key."""
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access_flag)

    def is_autostart_enabled(self, app_name: str) -> bool:
        """Check if application is in Windows startup."""
        try:
            with self._open_startup_registry(winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"Failed to check startup status for {app_name}: {e}")
            return False

    def enable_startup(self):
        if self.is_autostart_enabled(APP_NAME):
            print(f"{APP_NAME} is already set to start on boot.")
            return
        try:
            with self._open_startup_registry(winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f"{AUTOSTART_FILE}")
            print(f"{APP_NAME} added to startup.")
        except Exception as e:
            print(f"Failed to add {APP_NAME} to startup: {e}")

    def disable_startup(self):
        try:
            with self._open_startup_registry(winreg.KEY_ALL_ACCESS) as key:
                winreg.DeleteValue(key, APP_NAME)
            print(f"{APP_NAME} removed from startup.")
        except FileNotFoundError:
            print(f"Startup entry for {APP_NAME} not found.")
        except Exception as e:
            print(f"Failed to remove {APP_NAME} from startup: {e}")

    def parse_arguments(self):
        parser = CustomArgumentParser(
            description="The command-line interface for YASB Yike.",
            add_help=False,
            prog="yasbc",
        )
        subparsers = parser.add_subparsers(
            dest="command",
            help="Commands",
        )

        start_parser = subparsers.add_parser(
            "start",
            help="Start the application",
            prog="yasbc start",
        )
        start_parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            help="Silence print messages",
        )

        stop_parser = subparsers.add_parser(
            "stop",
            help="Stop the application",
            prog="yasbc stop",
        )
        stop_parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            help="Silence print messages",
        )
        stop_parser.add_argument(
            "-f",
            "--force",
            action="store_true",
            help="Force stop the application",
        )

        reload_parser = subparsers.add_parser(
            "reload",
            help="Reload the application",
            prog="yasbc reload",
        )
        reload_parser.add_argument(
            "-s",
            "--silent",
            action="store_true",
            help="Silence print messages",
        )

        enable_autostart_parser = subparsers.add_parser(
            "enable-autostart",
            help="Enable autostart on system boot",
            prog="yasbc enable-autostart",
        )
        enable_autostart_parser.add_argument(
            "--task",
            action="store_true",
            help="Enable autostart as a scheduled task",
        )

        disable_autostart_parser = subparsers.add_parser(
            "disable-autostart",
            help="Disable autostart on system boot",
            prog="yasbc disable-autostart",
        )
        disable_autostart_parser.add_argument(
            "--task",
            action="store_true",
            help="Disable autostart as a scheduled task",
        )

        subparsers.add_parser(
            "enable-crash-dumps",
            help="Enable crash dumps for troubleshooting",
            add_help=False,
        )

        subparsers.add_parser(
            "disable-crash-dumps",
            help="Disable crash dumps",
            add_help=False,
        )

        subparsers.add_parser(
            "monitor-information",
            help="Show information about connected monitors",
            add_help=False,
        )

        show_bar_parser = subparsers.add_parser(
            "show-bar",
            help="Show the bar on a specific screen",
            prog="yasbc show-bar",
        )
        show_bar_parser.add_argument(
            "-s",
            "--screen",
            type=str,
            help="Screen name (optional)",
        )

        hide_bar_parser = subparsers.add_parser(
            "hide-bar",
            help="Hide the bar on a specific screen",
            prog="yasbc hide-bar",
        )
        hide_bar_parser.add_argument(
            "-s",
            "--screen",
            type=str,
            help="Screen name (optional)",
        )

        toggle_bar_parser = subparsers.add_parser(
            "toggle-bar",
            help="Toggle the bar on a specific screen",
            prog="yasbc toggle-bar",
        )
        toggle_bar_parser.add_argument(
            "-s",
            "--screen",
            type=str,
            help="Screen name (optional)",
        )

        subparsers.add_parser(
            "config-dir",
            help="Open config directory in file explorer",
            add_help=False,
        )

        subparsers.add_parser(
            "help",
            help="Show help message",
            add_help=False,
        )
        subparsers.add_parser(
            "log",
            help="Tail yasb process logs (cancel with Ctrl-C)",
            add_help=False,
        )
        parser.add_argument(
            "-v",
            "--version",
            action="store_true",
            help="Show program's version number and exit.",
        )
        parser.add_argument(
            "-c",
            "--config",
            action="store_true",
            help="Print config directory path",
        )
        parser.add_argument(
            "-h",
            "--help",
            action="store_true",
            help="Show help message",
        )
        args = parser.parse_args()
        if args.command == "start":
            if not args.silent:
                print(
                    textwrap.dedent(f"""\
                    Start YASB Yike v{YASB_VERSION} in background.

                    # Project
                    * Repository https://github.com/uitTe/yike_yasb - report issues and share ideas
                    * Documentation https://github.com/uitTe/yike_yasb/tree/main/docs - how to configure and use YASB Yike

                    # Help
                    * Help https://github.com/uitTe/yike_yasb/tree/main/docs
                    * Thank you for using YASB Yike.
                """)
                )
            subprocess.Popen(["yasb.exe"])
            sys.exit(0)

        elif args.command == "stop":
            if args.force:
                for proc in ["yasb.exe"]:
                    if is_process_running(proc):
                        subprocess.run(["taskkill", "/f", "/im", proc], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                self.send_command_to_application("stop")
            sys.exit(0)
        elif args.command == "reload":
            if is_process_running("yasb.exe"):
                if not args.silent:
                    print("Reload YASB...")
                self.send_command_to_application("reload")
            else:
                print("YASB is not running. Reload aborted.")
            sys.exit(0)

        elif args.command == "show-bar":
            screen_arg = f" --screen {args.screen}" if args.screen else ""
            self.send_command_to_application(f"show-bar{screen_arg}")
            sys.exit(0)

        # For hide-bar command
        elif args.command == "hide-bar":
            screen_arg = f" --screen {args.screen}" if args.screen else ""
            self.send_command_to_application(f"hide-bar{screen_arg}")
            sys.exit(0)

        # For toggle-bar command
        elif args.command == "toggle-bar":
            screen_arg = f" --screen {args.screen}" if args.screen else ""
            self.send_command_to_application(f"toggle-bar{screen_arg}")
            sys.exit(0)

        elif args.command == "enable-autostart":
            if args.task:
                if not self.task_handler.is_admin():
                    print("Please run this command as an administrator.")
                else:
                    self.task_handler.create_task()
            else:
                self.enable_startup()
            sys.exit(0)

        elif args.command == "disable-autostart":
            if args.task:
                if not self.task_handler.is_admin():
                    print("Please run this command as an administrator.")
                else:
                    self.task_handler.delete_task()
            else:
                self.disable_startup()
            sys.exit(0)

        elif args.command == "enable-crash-dumps":
            if not self.task_handler.is_admin():
                print("Please run this command as an administrator.")
            else:
                self.crash_dump_handler.enable()
            sys.exit(0)

        elif args.command == "disable-crash-dumps":
            if not self.task_handler.is_admin():
                print("Please run this command as an administrator.")
            else:
                self.crash_dump_handler.disable()
            sys.exit(0)

        elif args.command == "log":
            print("Starting YASB log client. Press Ctrl+C to exit.")
            try:
                while True:
                    # Wait for the log pipe to be created
                    while True:
                        handle = CreateFile(
                            LOG_SERVER_PIPE_NAME,
                            GENERIC_READ | GENERIC_WRITE,
                            0,
                            None,
                            OPEN_EXISTING,
                            0,
                            None,
                        )
                        if handle != INVALID_HANDLE_VALUE:
                            break
                        time.sleep(0.1)

                    # Start reading the log stream
                    while True:
                        if not write_message(handle, {"type": "PING"}):
                            print(f"Failed to write PING. Err: {GetLastError()}")
                            break
                        for _ in range(2):
                            msg = read_message(handle)
                            if msg is None:
                                print(f"Failed to read message. Err: {GetLastError()}")
                                break
                            if msg.get("type") == "PONG":
                                break
                            elif msg.get("type") == "DATA":
                                print(msg.get("data"))
            except KeyboardInterrupt:
                print("\nExiting YASB log client.")

        elif args.command == "monitor-information":
            try:
                from PyQt6.QtGui import QGuiApplication
                from PyQt6.QtWidgets import QApplication

                app = QApplication([])

                screens = QGuiApplication.screens()
                primary_screen = QGuiApplication.primaryScreen()

                for i, screen in enumerate(screens, 1):
                    geometry = screen.geometry()
                    print(
                        textwrap.dedent(f"""\
                        {Format.underline}Monitor {i}:{Format.reset}
                          Name: {screen.name()}
                          Resolution: {geometry.width()}x{geometry.height()}
                          Position: ({geometry.left()},{geometry.top()}) to ({geometry.left() + geometry.width()},{geometry.top() + geometry.height()})
                          Primary: {"Yes" if screen == primary_screen else "No"}
                          Scale Factor: {screen.devicePixelRatio():.2f}
                          Manufacturer: {screen.manufacturer() or "Unknown"}
                          Model: {screen.model() or "Unknown"}
                    """)
                    )
                app.quit()
            except Exception as e:
                print(f"Error retrieving monitor information: {e}")

        elif args.command == "config-dir":
            try:
                subprocess.Popen(["explorer", DEFAULT_CONFIG_DIRECTORY])
            except Exception as e:
                print(f"Failed to open config directory: {e}")
            sys.exit(0)

        elif args.config:
            print(DEFAULT_CONFIG_DIRECTORY)
            sys.exit(0)

        elif args.command == "help" or args.help:
            print(
                textwrap.dedent(f"""\
                The command-line interface for YASB Yike.

                {Format.underline}Usage{Format.reset}: yasbc <COMMAND>

                {Format.underline}Commands{Format.reset}:
                  start                     Start the application
                  stop                      Stop the application
                  reload                    Reload the application
                  enable-autostart          Enable autostart on system boot
                  disable-autostart         Disable autostart on system boot
                  enable-crash-dumps        Enable crash dumps for troubleshooting
                  disable-crash-dumps       Disable crash dumps
                  monitor-information       Show information about connected monitors
                  show-bar                  Show the bar on all or a specific screen
                  hide-bar                  Hide the bar on all or a specific screen
                  toggle-bar                Toggle the bar on all or a specific screen
                  log                       Tail yasb process logs (cancel with Ctrl-C)
                  config-dir                Open config directory in file explorer
                  help                      Print this message

                {Format.underline}Options{Format.reset}:
                -v, --version  Print version
                -c, --config   Print config directory path
                -h, --help     Print this message
            """)
            )
            sys.exit(0)

        elif args.version:
            from core.utils.system import get_architecture

            architecture = get_architecture()
            arch_suffix = f" {architecture}" if architecture else ""
            version_message = (
                f"YASB Yike v{YASB_VERSION}{arch_suffix} ({YASB_RELEASE_CHANNEL})\nYASB-CLI v{YASB_CLI_VERSION}"
            )
            print(version_message)
        else:
            print("Unknown command. Use --help for available options.")
            sys.exit(1)


class CLICrashDumpHandler:
    """Turn Windows crash dumps for yasb.exe on or off.

    Windows logs crashes to the Event Viewer but doesn't save a dump file unless
    you ask it to, so there is usually nothing left to debug after a native crash.

    https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps
    """

    KEY_PATH = WER_LOCAL_DUMPS_KEY + "\\yasb.exe"
    DUMP_FOLDER = os.path.join(DEFAULT_CONFIG_DIRECTORY, "dumps")
    # Minidump missing some information, so we use a custom dump type with the following flags.
    # See https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps#custom-dump-flags
    DUMP_TYPE = 0  # 0 = custom (CUSTOM_DUMP_FLAGS), 1 = mini dump, 2 = full dump
    CUSTOM_DUMP_FLAGS = (
        MINIDUMP_WITH_DATA_SEGS  # module globals (WER default)
        | MINIDUMP_WITH_HANDLE_DATA  # handle table, so !handle works
        | MINIDUMP_WITH_UNLOADED_MODULES  # catches DLL-unload races (WER default)
        | MINIDUMP_WITH_INDIRECTLY_REFERENCED_MEMORY  # heap reachable from registers/stack
        | MINIDUMP_WITH_PROCESS_THREAD_DATA  # PEB/TEB (WER default)
        | MINIDUMP_WITH_FULL_MEMORY_INFO  # VA layout, so !address works
        | MINIDUMP_WITH_THREAD_INFO  # thread times and state
    )
    DUMP_COUNT = 5
    OWNS_PARENT_VALUE = "YasbCreatedLocalDumps"

    def _parent_key_exists(self) -> bool:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WER_LOCAL_DUMPS_KEY))
            return True
        except OSError:
            return False

    def enable(self):
        # An empty LocalDumps key is itself a switch that makes Windows dump every
        # application, and creating our key creates it too. Remember whether it was
        # already there so disable() only removes one we made.
        parent_existed = self._parent_key_exists()

        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, self.KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "DumpFolder", 0, winreg.REG_EXPAND_SZ, self.DUMP_FOLDER)
                winreg.SetValueEx(key, "DumpType", 0, winreg.REG_DWORD, self.DUMP_TYPE)
                winreg.SetValueEx(key, "CustomDumpFlags", 0, winreg.REG_DWORD, self.CUSTOM_DUMP_FLAGS)
                winreg.SetValueEx(key, "DumpCount", 0, winreg.REG_DWORD, self.DUMP_COUNT)
                if not parent_existed:
                    winreg.SetValueEx(key, self.OWNS_PARENT_VALUE, 0, winreg.REG_DWORD, 1)
        except OSError as e:
            print(f"Failed to enable crash dumps: {e}")
            return

        try:
            os.makedirs(self.DUMP_FOLDER, exist_ok=True)
        except OSError as e:
            print(f"Warning: could not create the dump directory: {e}")

        print("Crash dumps enabled.")
        print(f"Dumps will be saved to {self.DUMP_FOLDER}")
        print(f"The last {self.DUMP_COUNT} are kept. Attach the newest one when reporting a crash.")
        print("A dump is a snapshot of memory, so it can contain data from your config.")

    def disable(self):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.KEY_PATH) as key:
                created_parent = bool(winreg.QueryValueEx(key, self.OWNS_PARENT_VALUE)[0])
        except OSError:
            created_parent = False

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, self.KEY_PATH)
        except FileNotFoundError:
            print("Crash dumps are not enabled.")
            return
        except OSError as e:
            print(f"Failed to disable crash dumps: {e}")
            return

        # Only tear down LocalDumps if we were the ones who created it, and only while
        # nothing else has moved in since.
        if created_parent:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WER_LOCAL_DUMPS_KEY) as key:
                    subkeys, values, _ = winreg.QueryInfoKey(key)
                if not subkeys and not values:
                    winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, WER_LOCAL_DUMPS_KEY)
            except OSError:
                pass

        print("Crash dumps disabled. Existing dump files were left in place.")


class CLITaskHandler:
    """Handles tasks related to the command-line interface."""

    def is_admin(self):
        try:
            return IsUserAnAdmin()
        except BaseException:
            return False

    def get_current_user_sid(self):
        return get_current_user_sid()

    def create_task(self):
        scheduler = create_dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        task_def = scheduler.NewTask(0)
        task_def.RegistrationInfo.Description = "YASB Yike status bar."
        task_def.RegistrationInfo.Author = "shuf"
        task_def.Settings.Compatibility = 6
        trigger = task_def.Triggers.Create(9)
        trigger.Enabled = True
        trigger.StartBoundary = datetime.datetime.now().isoformat()
        principal = task_def.Principal
        principal.UserId = self.get_current_user_sid()
        principal.LogonType = 3
        principal.RunLevel = 0
        settings = task_def.Settings
        settings.Enabled = True
        settings.StartWhenAvailable = True
        settings.AllowHardTerminate = True
        settings.ExecutionTimeLimit = "PT0S"
        settings.Priority = 4
        settings.MultipleInstances = 3
        settings.DisallowStartIfOnBatteries = False
        settings.StopIfGoingOnBatteries = False
        settings.Hidden = False
        settings.RunOnlyIfIdle = False
        settings.DisallowStartOnRemoteAppSession = False
        settings.UseUnifiedSchedulingEngine = True
        settings.WakeToRun = False
        idle_settings = settings.IdleSettings
        idle_settings.StopOnIdleEnd = True
        idle_settings.RestartOnIdle = False
        action = task_def.Actions.Create(0)
        action.Path = EXE_PATH
        action.WorkingDirectory = SCRIPT_PATH
        try:
            root_folder.RegisterTaskDefinition("YASB Yike", task_def, 6, None, None, 3, None)
            print("Task YASB Yike created successfully.")
        except Exception as e:
            print(f"Failed to create task YASB Yike. Error: {e}")

    def delete_task(self):
        scheduler = create_dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        try:
            root_folder.DeleteTask("YASB Yike", 0)
            print("Task YASB Yike deleted successfully.")
        except Exception:
            print("Failed to delete task YASB Yike or task does not exist.")


if __name__ == "__main__":
    cli_handler = CLIHandler()
    cli_handler.parse_arguments()
    sys.exit(0)
