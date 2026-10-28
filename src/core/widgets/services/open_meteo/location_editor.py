"""天气弹窗的位置搜索与经纬度设置。"""

from PyQt6.QtCore import QLocale, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.ui.config_document import ConfigDocument
from core.validation.widgets.yasb.open_meteo import OpenMeteoLocationConfig
from core.widgets.services.open_meteo.api import GeocodingFetcher
from core.widgets.services.open_meteo.config import save_weather_location


class LocationEditor(QFrame):
    saved = pyqtSignal(object)
    cancelled = pyqtSignal()
    resized = pyqtSignal()

    def __init__(self, document: ConfigDocument, widget_name: str, current: dict | None, parent: QWidget):
        super().__init__(parent)
        self.setProperty("class", "location-editor")
        self._document = document
        self._widget_name = widget_name
        self._selected: OpenMeteoLocationConfig | None = None
        self._results: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.tabs = QTabWidget(self)
        self.tabs.setProperty("class", "location-tabs")
        layout.addWidget(self.tabs)

        search_page = QWidget()
        search_layout = QVBoxLayout(search_page)
        search_layout.setContentsMargins(0, 12, 0, 0)
        search_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.search = QLineEdit()
        self.search.setProperty("class", "search-input")
        self.search.setAccessibleName(tr("Search location"))
        self.search.setPlaceholderText(tr("Search city or location name"))
        self.search.setClearButtonEnabled(True)
        search_layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setProperty("class", "search-results")
        self.results.setAccessibleName(tr("Location search results"))
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setMinimumHeight(112)
        self.results.setMaximumHeight(160)
        self.results.hide()
        search_layout.addWidget(self.results)
        self.tabs.addTab(search_page, tr("Search location"))

        coordinates_page = QWidget()
        form = QFormLayout(coordinates_page)
        form.setContentsMargins(0, 12, 0, 0)
        form.setSpacing(10)
        self.name = QLineEdit()
        self.name.setMaxLength(80)
        self.name.setPlaceholderText(tr("Optional location name"))
        self.latitude = QLineEdit()
        self.longitude = QLineEdit()
        for control, title, minimum, maximum in (
            (self.latitude, tr("Latitude"), -90.0, 90.0),
            (self.longitude, tr("Longitude"), -180.0, 180.0),
        ):
            validator = QDoubleValidator(minimum, maximum, 6, control)
            locale = QLocale.c()
            locale.setNumberOptions(QLocale.NumberOption.RejectGroupSeparator)
            validator.setLocale(locale)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            control.setValidator(validator)
            control.setPlaceholderText(f"{minimum:g} … {maximum:g}")
            control.setAccessibleName(title)
            form.addRow(title, control)
        self.name.setAccessibleName(tr("Location name"))
        form.addRow(tr("Location name"), self.name)
        for control in (self.name, self.latitude, self.longitude):
            control.setProperty("class", "search-input")
        self.tabs.addTab(coordinates_page, tr("Custom coordinates"))
        if current:
            self.name.setText(current.get("name", ""))
            self.latitude.setText(f"{current['latitude']:.6f}")
            self.longitude.setText(f"{current['longitude']:.6f}")

        self.message = QLabel(tr("Enter at least two characters to search."))
        self.message.setProperty("class", "location-message")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton(tr("Cancel"))
        cancel.setProperty("class", "location-button")
        cancel.clicked.connect(self.cancelled)
        actions.addWidget(cancel)
        self.save = QPushButton(tr("Save"))
        self.save.setProperty("class", "location-button primary")
        self.save.setAccessibleName(tr("Save weather location"))
        self.save.setEnabled(False)
        self.save.clicked.connect(self._save)
        actions.addWidget(self.save)
        layout.addLayout(actions)

        self.fetcher = GeocodingFetcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._search)
        self.search.textChanged.connect(self._search_changed)
        self.search.returnPressed.connect(self._search)
        self.results.currentItemChanged.connect(self._select)
        self.fetcher.results_ready.connect(self._show_results)
        self.fetcher.search_failed.connect(self._search_failed)
        self.tabs.currentChanged.connect(self._mode_changed)
        for control in (self.name, self.latitude, self.longitude):
            control.textChanged.connect(self._validate)
        self._resize_tabs()

    def _resize_tabs(self):
        self.ensurePolished()
        page_height = self.tabs.currentWidget().sizeHint().height()
        self.tabs.setFixedHeight(self.tabs.tabBar().sizeHint().height() + page_height)
        self.updateGeometry()
        QTimer.singleShot(0, self.resized.emit)

    def _mode_changed(self):
        self._debounce.stop()
        self.fetcher.cancel()
        self._validate()
        self._resize_tabs()

    def _search_changed(self):
        self.fetcher.cancel()
        self._selected = None
        self.results.clear()
        self.results.hide()
        self.save.setEnabled(False)
        self.message.setText(tr("Enter at least two characters to search."))
        self._debounce.start()
        self._resize_tabs()

    def _search(self):
        self._debounce.stop()
        query = self.search.text().strip()
        if len(query) < 2:
            return
        self.message.setText(tr("Searching locations..."))
        self.fetcher.search(query)

    def _show_results(self, results: list[dict]):
        self._results = results
        self.results.clear()
        for result in results:
            parts = dict.fromkeys(result.get(key, "") for key in ("name", "admin2", "admin1", "country"))
            title = ", ".join(part for part in parts if part)
            item = QListWidgetItem(f"{title}\n{result['latitude']:.6f}, {result['longitude']:.6f}")
            self.results.addItem(item)
        self.results.setVisible(bool(results))
        self.message.setText(tr("Select a location, then save.") if results else tr("No locations found."))
        self._resize_tabs()

    def _select(self, item: QListWidgetItem | None):
        self._selected = None
        if item is not None:
            result = self._results[self.results.row(item)]
            self._selected = OpenMeteoLocationConfig(
                name=result["name"], latitude=result["latitude"], longitude=result["longitude"])
        self._validate()

    def _search_failed(self, reason: str):
        self.message.setText(tr("Location search failed: {reason}", reason=reason))
        self.resized.emit()

    def _validate(self):
        if self.tabs.currentIndex() == 0:
            valid = self._selected is not None
            self.message.setText(tr("Select a location, then save.") if valid
                                 else tr("Enter at least two characters to search."))
        else:
            valid = self.latitude.hasAcceptableInput() and self.longitude.hasAcceptableInput()
            self.message.setText(tr("Latitude: -90 to 90. Longitude: -180 to 180."))
        self.save.setEnabled(valid)

    def _save(self):
        self._validate()
        if not self.save.isEnabled():
            return
        if self._document.path.read_bytes() != self._document.original_bytes:
            self.message.setText(tr("Configuration changed. Reopen location settings to load it again."))
            self.save.setEnabled(False)
            return
        location = self._selected
        if self.tabs.currentIndex() == 1:
            latitude, longitude = float(self.latitude.text()), float(self.longitude.text())
            location = OpenMeteoLocationConfig(
                name=self.name.text().strip() or f"{latitude:.6f}, {longitude:.6f}",
                latitude=latitude, longitude=longitude)
        assert location is not None
        save_weather_location(self._document, self._widget_name, location)
        self.saved.emit(location)
