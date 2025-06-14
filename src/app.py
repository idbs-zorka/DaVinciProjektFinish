from PySide6.QtCore import Slot, Signal
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout  # Biblioteka graficzna

from gui.station_details import StationDetailsWidget
from gui.station_select import StationSelectWidget
from repository import Repository


class Application(QApplication):
    station_select: StationSelectWidget
    station_details: StationDetailsWidget

    api_connection_status_changed = Signal(bool)


    def __init__(self,repository: Repository,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.repository = repository

        api_client = self.repository.api_client()
        api_client.connection_status_changed = self.on_api_connection_status_changed

    def on_api_connection_status_changed(self,value: bool):
        self.api_connection_status_changed.emit(value)

    def exec(self):
        self.station_select = StationSelectWidget(self.repository)
        self.station_select.stationSelected.connect(self.open_station_details)
        self.station_select.show()
        return super().exec()

    @Slot(int)
    def open_station_details(self,station_id: int):
        dialog = QDialog(self.station_select)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        self.station_details = StationDetailsWidget(self.repository, station_id, dialog)
        layout.addWidget(self.station_details)
        dialog.show()
