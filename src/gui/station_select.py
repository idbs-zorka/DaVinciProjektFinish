import logging
from dataclasses import dataclass
from typing import Sequence, cast, TYPE_CHECKING

from PySide6.QtCore import Signal, Slot, Qt, QThreadPool, QRunnable, QObject
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QWidget, QLineEdit, QComboBox, QFormLayout, QListWidget, QVBoxLayout, QHBoxLayout, \
    QListWidgetItem, QMainWindow, QStatusBar, QLabel, QApplication, QMessageBox, QCheckBox, QSpacerItem
from geopy.distance import distance

from src import location
from src.config import AQ_TYPES, AQ_INDEX_CATEGORIES_COLORS, AQ_INDEX_CATEGORIES
from src.database.views import StationListView
from src.fuzzy_seach import fuzzy_search
from src.gui.station_map_view import StationMapViewWidget
from src.repository import Repository

# Musi tak być aby uniknąć zależności cyklicznej
if TYPE_CHECKING:
    from src.app import Application

@dataclass
class FilterState:
    search_query: str
    city: str | None
    search_by_location: bool
    range: int

class StationSelectFilter(QWidget):
    filter_changed = Signal(FilterState)

    def __init__(self,cities: Sequence[str],*args,**kwargs):
        super().__init__()

        self.search_query_input = QLineEdit(self)
        self.search_query_input.textChanged.connect(self._on_query_changed)
        self.search_query_input.editingFinished.connect(self._on_query_edit_finished)

        # Searching by location

        self.search_by_location_checkbox = QCheckBox("Szukaj po lokalizacji", self)
        self.search_by_location_checkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.location_range = QComboBox(self,editable=True)
        self.location_range.lineEdit().setValidator(QIntValidator(10,100))
        self.location_range.setEnabled(False)

        self.location_range.addItems(("5","10","30","50","100"))
        self.location_range.setCurrentText("10")

        location_range_label = QLabel("Km",self)

        self.search_by_location_layout = QHBoxLayout()

        self.search_by_location_layout.addWidget(self.search_by_location_checkbox)
        self.search_by_location_layout.addStretch(1)
        self.search_by_location_layout.addWidget(self.location_range)
        self.search_by_location_layout.addWidget(location_range_label)

        # Signals

        self.search_by_location_checkbox.stateChanged.connect(lambda x: self.location_range.setEnabled(x))
        self.search_by_location_checkbox.stateChanged.connect(self._on_filter_changed)

        self.location_range.currentTextChanged.connect(self._on_filter_changed)

        self.city_combo = QComboBox(self)
        self.city_combo.addItems(["Wybierz miasto", *cities])
        self.city_combo.currentIndexChanged.connect(self._on_filter_changed)

        self.layout = QFormLayout(self) # Tworzenie elementu: Text:Element
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.addRow("Szukaj", self.search_query_input)
        self.layout.addRow("", self.search_by_location_layout)
        self.layout.addRow("Miasto", self.city_combo)

    def current_city(self):
        return self.city_combo.currentText() if self.city_combo.currentIndex() > 0 else None

    @Slot()
    def _on_filter_changed(self):
        self.filter_changed.emit(
            FilterState(
                search_query=self.search_query_input.text(),
                city=self.current_city(),
                search_by_location=self.search_by_location_checkbox.isChecked(),
                range=int(self.location_range.currentText())
            )
        )

    @Slot()
    def _on_query_changed(self):
        if not self.search_by_location_checkbox.isChecked():
            self._on_filter_changed()

    @Slot()
    def _on_query_edit_finished(self):
        self._on_filter_changed()



class StationIndexFetcher(QRunnable):
    class Signals(QObject):
        finished = Signal(int,int)

    def __init__(self,station_id: int,index_type: str,repository: Repository):
        logging.info(f"Fetcher created: station_id:  {station_id}, index_type: {index_type}")
        super().__init__()
        self.station_id = station_id
        self.index_type = index_type
        self.repository = repository
        self.signals = self.Signals()

    def run(self):
        own_repository = self.repository.clone()
        value = own_repository.fetch_station_air_quality_index_value(self.station_id,self.index_type)

        if value is None:
             value = -1

        self.signals.finished.emit(self.station_id,value)


class StationSelectWidget(QMainWindow):
    stationSelected = Signal(int)

    def __init__(self, repository: Repository, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.repository = repository

        self.thread_pool = QThreadPool.globalInstance()

        # Główny layout HBox
        main = QWidget(self)

        # LEWA CZĘŚĆ
        left = QWidget(main)
        left.setMinimumSize(350,450)
        left_layout = QVBoxLayout(left)

        self.stations = repository.get_station_list_view()
        self.filtered_stations = self.stations

        cities = sorted({st.city for st in self.stations})

        self.select_filter_widget = StationSelectFilter(parent=left, cities=cities)
        self.select_filter_widget.filter_changed.connect(self.on_filter_changed)

        self.stations_list_widget = QListWidget(left)
        self.set_station_list_items(self.stations)
        self.stations_list_widget.itemClicked.connect(self.on_station_clicked)
        self.stations_list_widget.itemDoubleClicked.connect(self.on_station_double_clicked)

        left_layout.addWidget(self.select_filter_widget)
        left_layout.addWidget(self.stations_list_widget)

        # PRAWA CZĘŚĆ
        right = QWidget(main,visible=False)
        self.right = right
        right.setMinimumSize(800,600)
        right_layout = QVBoxLayout(right)

        # Formularz wyboru typu indeksu jakości powietrzna
        aq_index_type_form = QFormLayout()
        self.aq_index_type_combo = QComboBox()
        self.aq_index_type_combo.addItems(AQ_TYPES)
        self.aq_index_type_combo.currentIndexChanged.connect(self.on_aq_index_changed)
        aq_index_type_form.addRow("Indeks:", self.aq_index_type_combo)

        # Widget mapy
        self.map_view = StationMapViewWidget(parent=right)
        self.map_view.leaftletLoaded.connect(lambda : right.setVisible(True))
        self.map_view.web.loadFinished.connect(self.on_map_loaded)
        self.map_view.stationSelected.connect(self.on_station_marker_clicked)
        self.map_view.requestStationIndexValue.connect(self.on_request_station_index_value)


        right_layout.addLayout(aq_index_type_form, stretch=0)
        right_layout.addWidget(self.map_view, stretch=1)

        # DODANIE DO GŁÓWNEGO
        main_layout = QHBoxLayout(main)

        main_layout.addWidget(left, 0)  # lewy panel bez stretchu
        main_layout.addWidget(right, 1)  # prawy panel z większym stretchem

        # wyrównanie elementów
        main_layout.setStretchFactor(left, 0)
        main_layout.setStretchFactor(right, 1)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.setCentralWidget(main)

        # Status bar

        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)
        self.connection_status_label = QLabel("Status danych: {}")
        status_bar.addPermanentWidget(self.connection_status_label)

        # Wymuszenie sprawdzenia połączenia z api
        connection_status = self.repository.api_client().connection_status
        self.on_api_connection_status_changed(connection_status)

        app = cast('Application',QApplication.instance())
        app.api_connection_status_changed.connect(self.on_api_connection_status_changed)


    @Slot(bool)
    def on_api_connection_status_changed(self,value: bool):
        text = "Aktualne" if value else "Lokalne"
        self.connection_status_label.setText(f"Status danych: {text}")

        if value == False:
            QMessageBox.warning(
                self,
                "Brak połączenia",
                "Utracono połączenie z serwerem.\n"
                "Aplikacja będzie działać w trybie offline i będzie korzystać z zapisanych danych lokalnych."
            )

    def center(self):
        # Get screen geometry
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()

        # Get the size of the window
        window_geometry = self.frameGeometry()

        # Center point of the screen
        center_point = screen_geometry.center()

        # Move the rectangle's center to the screen center
        window_geometry.moveCenter(center_point)

        # Move the top-left of the window to match the centered rect
        self.move(window_geometry.topLeft())


    @Slot()
    def on_map_loaded(self):
        self.setup_markers()
        self.center()


    @Slot(FilterState)
    def on_filter_changed(self,state: FilterState):
        self.filtered_stations = self.stations
        if state.city is not None:
            self.filtered_stations = [
                st for st in self.filtered_stations
                if st.city == state.city
            ]

        if state.search_query != '':
            if state.search_by_location: # Szukaj po lokalizacji
                (lat,lng) = location.find_position(state.search_query)
                self.map_view.set_position(lat,lng)
                self.filtered_stations = [
                    st for st in self.filtered_stations
                    if distance((lat,lng),(st.latitude,st.longitude)).km <= state.range
                ]
            else: # Szukaj po nazwie
                name_to_station = {
                    st.name: st for st in self.filtered_stations
                }
                searched = fuzzy_search(state.search_query,name_to_station.keys(),score_cutoff=60)
                self.filtered_stations = [
                name_to_station[result] for result in searched
                ]
        else:
            self.filtered_stations.sort(key=lambda x: x.name)

        self.set_station_list_items(self.filtered_stations)

    def set_station_list_items(self,stations: list[StationListView]):
        self.stations_list_widget.clear()

        for st in stations:
            item = QListWidgetItem(st.name,listview=self.stations_list_widget)
            item.setData(Qt.ItemDataRole.UserRole,st)

    def setup_markers(self):
        for st in self.stations:
            self.map_view.add_station(st.latitude,st.longitude,st.id)

    @Slot(QListWidgetItem)
    def on_station_double_clicked(self,item: QListWidgetItem):
        station = item.data(Qt.ItemDataRole.UserRole)
        self.stationSelected.emit(station.id)

    @Slot(QListWidgetItem)
    def on_station_clicked(self,item: QListWidgetItem):
        station = item.data(Qt.ItemDataRole.UserRole)
        self.map_view.set_position(station.latitude,station.longitude)

    @Slot(int)
    def on_station_marker_clicked(self,station_id: int):
        self.stationSelected.emit(station_id)

    @Slot(int)
    def on_aq_index_changed(self,index: int):
        self.map_view.reset_indexes()

    @Slot(int)
    def on_request_station_index_value(self,station_id: int):
        current_index = self.aq_index_type_combo.currentText()

        task = StationIndexFetcher(station_id,current_index,self.repository)
        task.signals.finished.connect(self.map_view.init_index_value)

        self.thread_pool.start(task)
