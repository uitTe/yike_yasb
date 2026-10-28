"""创建独立进程中的真实窗口，供窗口关闭检查使用。"""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication([])
window = QWidget()
window.setWindowTitle(sys.argv[1])
window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
window.resize(280, 140)
window.move(300, 200)
window.show()
print(int(window.winId()), flush=True)
sys.exit(app.exec())
