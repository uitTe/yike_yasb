from collections import deque

from humanize import naturalsize
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from core.utils.stat_popup import GraphWidget, PinnablePopup, build_stat_popup
from core.utils.utilities import PopupWidget
from core.validation.widgets.yasb.system_monitor import SystemMonitorConfig
from core.widgets.base import BaseWidget
from core.widgets.services.cpu.cpu_api import CpuData, CpuWorker
from core.widgets.services.memory.memory_api import MemoryData, MemoryWorker


class SystemMonitorWidget(BaseWidget):
    validation_schema = SystemMonitorConfig

    def __init__(self, config: SystemMonitorConfig):
        super().__init__(class_name=f"system-monitor-widget {config.class_name}")
        self.config = config
        self._cpu_data: CpuData | None = None
        self._memory_data: MemoryData | None = None
        self._cpu_history: deque[float] = deque(maxlen=config.menu.graph_history_size)
        self._memory_history: deque[float] = deque(maxlen=config.menu.graph_history_size)
        self._init_container()
        self.build_widget_label("<span>\ueea1</span> CPU … <span>\ue9d9</span> 内存 …")
        self._widget_container_layout.setSpacing(4)
        self.register_callback("toggle_menu", self._toggle_menu)
        self.callback_left = config.callbacks.on_left
        self.callback_middle = config.callbacks.on_middle
        self.callback_right = config.callbacks.on_right
        self.setAccessibleName("CPU和内存")
        self._cpu_worker = CpuWorker.get_instance(config.update_interval)
        self._memory_worker = MemoryWorker.get_instance(config.update_interval)
        self._cpu_worker.data_ready.connect(self._on_cpu_data)
        self._memory_worker.data_ready.connect(self._on_memory_data)
        for worker in (self._cpu_worker, self._memory_worker):
            if not worker.isRunning():
                worker.start()

    def _on_cpu_data(self, data: CpuData):
        self._cpu_data = data
        self._cpu_history.append(data.percent)
        self._widgets[1].setText(f"CPU {data.percent:.0f}%")
        self._update_popup()

    def _on_memory_data(self, data: MemoryData):
        self._memory_data = data
        self._memory_history.append(data.virtual.percent)
        self._widgets[3].setText(f"内存 {data.virtual.percent:.0f}%")
        self._update_popup()

    def _values(self) -> dict[str, str]:
        cpu = self._cpu_data
        memory = self._memory_data
        size = lambda value: naturalsize(value, binary=True, format="%.1f").replace("i", "")
        return {
            "cpu": f"{cpu.percent:.0f}%" if cpu else "等待数据",
            "frequency": f"{cpu.freq.current:.0f} MHz" if cpu else "等待数据",
            "cores": f"{cpu.cores_physical} / {cpu.cores_logical}" if cpu else "等待数据",
            "maximum": f"{cpu.freq.max:.0f} MHz" if cpu else "等待数据",
            "memory": f"{memory.virtual.percent:.0f}%" if memory else "等待数据",
            "used": size(memory.virtual.used) if memory else "等待数据",
            "total": size(memory.virtual.total) if memory else "等待数据",
            "available": size(memory.virtual.available) if memory else "等待数据",
            "cached": size(memory.cached_bytes) if memory else "等待数据",
            "swap": size(memory.swap.used) if memory else "等待数据",
        }

    def _toggle_menu(self):
        if not self.config.menu.enabled:
            return
        previous = PopupWidget.open_popup_for(self)
        if previous is not None and previous.isVisible():
            previous.hide_animated()
            return
        values = self._values()
        rows = [
            ("CPU 使用率", "cpu", values["cpu"], "当前频率", "frequency", values["frequency"]),
            ("核心 / 逻辑处理器", "cores", values["cores"], "最高频率", "maximum", values["maximum"]),
            ("内存使用率", "memory", values["memory"], "已用内存", "used", values["used"]),
            ("全部内存", "total", values["total"], "可用内存", "available", values["available"]),
            ("缓存内存", "cached", values["cached"], "交换空间", "swap", values["swap"]),
        ]
        popup = build_stat_popup(
            parent=self, menu_config=self.config.menu, popup_class_name="cpu-popup system-monitor-popup",
            title="CPU 与内存", history=self._cpu_history, stat_rows=rows, graph_class="cpu-graph",
        )
        if popup.graph is not None:
            layout = popup.layout()
            cpu_title = QLabel("CPU 使用率")
            cpu_title.setProperty("class", "graph-title")
            layout.insertWidget(1, cpu_title)
            container = QFrame(popup)
            container.setProperty("class", "graph-container")
            graph_layout = QVBoxLayout(container)
            graph_layout.setContentsMargins(0, 0, 0, 0)
            memory_graph = GraphWidget("memory-graph", show_grid=self.config.menu.show_graph_grid)
            graph_layout.addWidget(memory_graph)
            memory_graph.set_data(list(self._memory_history))
            title = QLabel("内存使用率")
            title.setProperty("class", "graph-title")
            layout.insertWidget(3, title)
            layout.insertWidget(4, container)
        popup.adjustSize()
        popup.setPosition(
            alignment=self.config.menu.alignment, direction=self.config.menu.direction,
            offset_left=self.config.menu.offset_left, offset_top=self.config.menu.offset_top,
        )
        popup.show()

    def _update_popup(self):
        popup = PopupWidget.open_popup_for(self)
        if not isinstance(popup, PinnablePopup) or not popup.isVisible():
            return
        for name, value in self._values().items():
            popup.stat_labels[name].setText(value)
        if popup.graph is not None:
            popup.graph.set_data(list(self._cpu_history))
            memory_graph = next(graph for graph in popup.findChildren(GraphWidget) if graph is not popup.graph)
            memory_graph.set_data(list(self._memory_history))
