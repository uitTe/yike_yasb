"""真实作业对象验证使用的进程入口。"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.utils.process import start_independent_process


def main() -> None:
    mode, directory, *arguments = sys.argv[1:]
    output = Path(directory)
    if mode == "launcher":
        child_command = [sys.executable, __file__, "child", directory, *arguments]
        normal = subprocess.Popen(child_command + ["normal"], creationflags=subprocess.CREATE_NO_WINDOW)
        independent = start_independent_process(child_command + ["independent"])
        (output / "launcher.json").write_text(json.dumps({"normal": normal.pid, "independent": independent}))
    else:
        (output / f"{arguments[-1]}.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "cwd": os.getcwd(),
                    "parent": os.getppid(),
                    "arguments": arguments[:-1],
                    "environment": os.environ["YASB_LIFETIME_TEST"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    time.sleep(120)


if __name__ == "__main__":
    main()
