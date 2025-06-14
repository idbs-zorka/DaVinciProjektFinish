from pathlib import Path

from PySide6.QtCore import QObject, Slot, QUrl, Signal
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout

from src.config import AQ_INDEX_CATEGORIES_COLORS, AQ_INDEX_CATEGORIES


class MapViewBackend(QObject):

    @Slot(result=int)
    def get_color_by_value(self,scale_id: int) -> int:
        return AQ_INDEX_CATEGORIES_COLORS.get(scale_id) or 0

    # Python wysyla do mapy
    #               latitude, longitude, id
    addStation = Signal(float, float, int)
    setPosition = Signal(float, float)
    resetIndexes = Signal()
    #                   station_id, index_value
    initIndexValue = Signal(int, int)

    # Mapa wysyla do pythona
    stationSelected = Signal(int)
    @Slot(int)
    def on_station_selected(self,station_id: int):
        self.stationSelected.emit(station_id)

    requestStationIndexValue = Signal(int)
    @Slot(int)
    def request_station_index_value(self,station_id: int):
        print(f"Request station index value: {station_id}")
        self.requestStationIndexValue.emit(station_id)

    leaftletLoaded = Signal()
    @Slot()
    def on_leaflet_load(self):
        self.leaftletLoaded.emit()


class StationMapViewWidget(QWidget):

    backend : MapViewBackend # Na potrzeby integracji JavaScript

    def __init__(self,parent = None):
        super().__init__(parent=parent)

        # silnik przeglądarki

        web = QWebEngineView(parent=self)

        self.backend = MapViewBackend()

        map_path = Path(__file__).with_name("station_map_view.html").resolve()

        web.settings().setAttribute(web.settings().WebAttribute.LocalContentCanAccessRemoteUrls,True) #Ustawianie mozliwosci komunikacji sieciowej dla widgetu
        self.channel = QWebChannel()

        page = web.page()
        page.setWebChannel(self.channel)
        self.channel.registerObject("backend",self.backend) # Przekazanie obiektu do JavaScriptu

        self.stationSelected = self.backend.stationSelected
        self.requestStationIndexValue = self.backend.requestStationIndexValue
        self.leaftletLoaded = self.backend.leaftletLoaded
        web.load(QUrl.fromLocalFile(map_path))

        self.web = web

        # Skala
        color_scale = QWidget(self)
        color_scale_layout = QHBoxLayout(color_scale)
        color_scale_layout.setSpacing(0)
        color_scale_layout.setContentsMargins(0,0,0,0)

        color_scale_list = list(AQ_INDEX_CATEGORIES_COLORS.items())
        color_scale_list.sort(key=lambda x:x[0])

        for (val,color) in color_scale_list:
            label = QLabel(AQ_INDEX_CATEGORIES[val], color_scale)
            label.setStyleSheet(f"background-color: #{color:06x}")
            color_scale_layout.addWidget(label,1)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(web,stretch=1)
        layout.addWidget(color_scale)


    def add_station(self,lat: float,lng:float,station_id: int):
        self.backend.addStation.emit(lat,lng,station_id)

    def reset_indexes(self):
        self.backend.resetIndexes.emit()

    def set_position(self,lat: float,lng: float):
        self.backend.setPosition.emit(lat,lng)

    @Slot(int,int)
    def init_index_value(self,station_id: int,value: int):
        self.backend.initIndexValue.emit(station_id,value)