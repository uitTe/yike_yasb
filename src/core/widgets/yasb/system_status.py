import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from winrt.windows.networking.connectivity import NetworkInformation

from core.utils.qobject import is_valid_qobject
from core.validation.widgets.yasb.system_status import SystemStatusConfig
from core.widgets.services.battery.battery_api import BatteryAPI
from core.widgets.yasb.control_center import ControlCenterWidget


class SystemStatusWidget(ControlCenterWidget):
    validation_schema = SystemStatusConfig
    popup_class_name = "control-center-menu system-status-menu"

    def __init__(self, config: SystemStatusConfig):
        self._status_ready = False
        super().__init__(config)
        self._widget_frame.setProperty("class", f"widget system-status-widget {config.class_name}")
        self._status_labels: dict[str, QLabel] = {}
        self._detail_labels: dict[str, QLabel] = {}
        self._widget_container_layout.setSpacing(4)
        for name in ("wifi", "volume", "battery"):
            label = QLabel()
            label.setProperty("class", "icon")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._widget_container_layout.addWidget(label)
            self._status_labels[name] = label
        self.setAccessibleName("Wi-Fi、音量和电量")
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(config.update_interval)
        self._status_timer.timeout.connect(self._update_status)
        self._status_ready = True
        self._status_timer.start()
        self._update_status()

    def _update_status(self):
        if not self._status_ready:
            return
        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            network = "网络未连接"
            wifi_icon = "\ue871"
        elif profile.is_wlan_connection_profile:
            bars = profile.get_signal_bars()
            wifi_icon = ("\ue871", "\ue872", "\ue873", "\ue874", "\ue701")[bars if bars is not None else 0]
            network = f"Wi-Fi：{profile.profile_name}"
        else:
            wifi_icon = "\ue839"
            network = f"以太网：{profile.profile_name}"

        output = self._output_service.get_volume_interface() if self._output_service else None
        microphone = self._input_service.get_microphone_interface() if self._input_service else None
        volume_muted = bool(output.GetMute()) if output is not None else None
        mic_muted = bool(microphone.GetMute()) if microphone is not None else None
        volume = f"{round(output.GetMasterVolumeLevelScalar() * 100)}%" if output is not None else "无输出设备"
        mic_level = f"{round(microphone.GetMasterVolumeLevelScalar() * 100)}%" if microphone is not None else "无输入设备"
        self._status_labels["wifi"].setText(wifi_icon)
        self._status_labels["volume"].setText("\ue74f" if volume_muted or output is None else "\ue767")

        battery = BatteryAPI.instance().get_status()
        if battery is None:
            battery_text = "未检测到电池"
            self._status_labels["battery"].setVisible(False)
        else:
            state = "正在充电" if battery.is_charging else "已接通电源" if battery.power_plugged else "使用电池"
            battery_text = f"电量：{battery.percent}% · {state}"
            if battery.time_remaining >= 0:
                minutes = battery.time_remaining // 60
                battery_text += f" · 剩余 {minutes // 60} 小时 {minutes % 60} 分钟"
            self._status_labels["battery"].setText("\ue83e" if battery.power_plugged else "\ue850")
            self._status_labels["battery"].setVisible(True)

        details = {
            "wifi": network,
            "volume": f"声音：{volume}" + (" · 已静音" if volume_muted else ""),
            "microphone": f"麦克风：{mic_level}" + (" · 已静音" if mic_muted else ""),
            "battery": battery_text,
        }
        self.setToolTip("\n".join(details.values()))
        for name, label in self._detail_labels.items():
            label.setText(details[name])

    def _show_menu(self):
        create_details = self.dialog is None or not is_valid_qobject(self.dialog)
        super()._show_menu()
        if create_details:
            section = QFrame(self.dialog)
            section.setProperty("class", "section connectivity")
            layout = QVBoxLayout(section)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            for name in ("wifi", "volume", "microphone", "battery"):
                label = QLabel(section)
                label.setProperty("class", "status-detail")
                layout.addWidget(label)
                self._detail_labels[name] = label
            buttons = QHBoxLayout()
            for title, uri in (("管理 Wi-Fi", "ms-availablenetworks:"), ("电池设置", "ms-settings:batterysaver")):
                button = QPushButton(title, section)
                button.setProperty("class", "settings-button")
                button.clicked.connect(lambda checked=False, uri=uri: self._open_settings(uri))
                buttons.addWidget(button)
            layout.addLayout(buttons)
            self.dialog.layout().insertWidget(0, section)
        self._update_status()
        self.dialog.adjustSize()
        self.dialog.setPosition(
            alignment=self.config.popup.alignment,
            direction=self.config.popup.direction,
            offset_left=self.config.popup.offset_left,
            offset_top=self.config.popup.offset_top,
        )

    def _open_settings(self, uri: str):
        self.dialog.hide()
        os.startfile(uri)

    def _refresh_audio_state(self):
        super()._refresh_audio_state()
        self._update_status()

    def _reinitialize_audio(self):
        super()._reinitialize_audio()
        self._update_status()

    def _reinitialize_microphone(self):
        super()._reinitialize_microphone()
        self._update_status()
