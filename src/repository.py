import logging
from datetime import datetime, timedelta

import requests.exceptions

import src.database.views as views
from src.api.client import Client as APIClient
from src.config import UPDATE_INTERVALS
from src.database.client import Client as DatabaseClient


class Repository:
    """
    Repozytorium odpowiedzialne za pobieranie danych ze zdalnego API
    i synchronizację ich z lokalną bazą danych.

    Metody w klasie zapewniają:
      - aktualizację listy stacji,
      - pobieranie widoku listy stacji,
      - pobieranie i aktualizację szczegółowych danych jakości powietrza dla konkretnej stacji.
    """

    def __init__(self, api_client: APIClient, database_client: DatabaseClient):
        """
        Inicjalizuje instancję repozytorium.

        Args:
            api_client (api.Client): Klient do komunikacji z zewnętrznym API.
            database_client (database.Client): Klient do operacji na lokalnej bazie danych.
        """
        self._api_client = api_client
        self._database_client = database_client

    def api_client(self):
        return self._api_client

    def clone(self):
        return Repository(self._api_client,self._database_client.duplicate_connection())

    # Ta fukcja nie jest prywatna poniewaz moze sluzyc do odswierzenia
    def update_stations(self):
        """
        Pobiera aktualną listę stacji z API i zapisuje ją w bazie danych.

        Sekwencja działań:
          1. Wywołanie `fetch_stations()` na kliencie API.
          2. Przekazanie pobranych danych do `update_stations()` klienta bazy.
        """

        api_stations = self._api_client.fetch_stations()

        self._database_client.update_stations(
            stations=api_stations
        )

    def get_station_list_view(self) -> list[views.StationListView]:
        """
        Zwraca widok listy stacji, odświeżając dane jeśli upłynął zdefiniowany interwał.

        Jeśli od ostatniej aktualizacji minął czas określony w `UPDATE_INTERVALS['station']`,
        następuje wywołanie `update_stations()`.

        Returns:
            list[database.views.StationListView]: Lista obiektów widoku stacji.
        """
        last_update_at = self._database_client.get_last_stations_update()
        elapsed = datetime.now() - last_update_at

        try:
            if elapsed >= UPDATE_INTERVALS['station']:
                self.update_stations()
        except requests.exceptions.ConnectionError as e:
            logging.warning("Error while updating stations: %s",e)

        return self._database_client.get_station_list_view()


    def fetch_station_details_view(self, station_id: int) -> views.StationDetailsView:
        last_update_at = self._database_client.get_last_stations_update()
        elapsed = datetime.now() - last_update_at

        try:
            if elapsed >= UPDATE_INTERVALS['station']:
                self.update_stations()
        except requests.exceptions.ConnectionError as e:
            logging.warning("Error while updating stations: %s",e)

        return self._database_client.fetch_station_detail_view(station_id)

    # Ta fukcja nie jest prywatna poniewaz moze sluzyc do odswierzenia
    def update_station_air_quality_indexes(self, station_id: int):
        """
        Pobiera i aktualizuje wskaźniki jakości powietrza dla danej stacji.

        Args:
            station_id (int): Identyfikator stacji.
        """
        air_quality_indexes = self._api_client.fetch_air_quality_indexes(station_id)

        self._database_client.update_station_air_quality_indexes(
            station_id=station_id,
            indexes=air_quality_indexes
        )

    def fetch_station_air_quality_index_value(self, station_id: int,type_codename: str) -> int:
        """
        Zwraca listę wskaźników jakości powietrza, odświeżając dane
        gdy minął określony interwał czasu.

        Args:
            station_id (int): Identyfikator stacji.

        Returns:
            list[database.views.AQIndexView]: Lista obiektów widoku wskaźników jakości powietrza.
        """
        last_update_at = self._database_client.fetch_last_station_air_quality_indexes_update(station_id)
        elapsed = datetime.now() - last_update_at

        try:
            if elapsed >= UPDATE_INTERVALS['aq_indexes']:
                self.update_station_air_quality_indexes(station_id)
        except requests.exceptions.ConnectionError as e:
            logging.warning("Error while updating air quality index values: %s",e)

        return self._database_client.fetch_station_air_quality_index_value(station_id, type_codename)

    def update_station_sensors(self,station_id: int):
        stations = self._api_client.fetch_station_sensors(station_id)
        self._database_client.update_station_sensors(station_id, stations)

    def fetch_station_sensors(self,station_id: int) -> list[views.SensorView]:
        last_update_at = self._database_client.fetch_last_station_sensors_update(station_id)
        elapsed = datetime.now() - last_update_at

        try:
            if elapsed >= UPDATE_INTERVALS['sensors']:
                self.update_station_sensors(station_id)
        except requests.exceptions.ConnectionError as e:
            logging.warning("Error while updating station sensors: %s",e)

        return self._database_client.fetch_station_sensors(station_id)


    def update_sensor_data(self,sensor_id: int,date_from: datetime,date_to: datetime):
        now = datetime.now()
        from_delta = (now - date_from)

        if from_delta >= timedelta(days=3,hours=1):
            data = self._api_client.fetch_sensor_archival_data(
                sensor_id=sensor_id,
                date_from=date_from,
                date_to=date_to
            )
            self._database_client.update_sensor_data(sensor_id, data)

        to_delta = (now - date_to)

        if to_delta <= timedelta(days=3,hours=1):
            data = self._api_client.fetch_sensor_data(sensor_id)
            self._database_client.update_sensor_data(sensor_id, data)


    def fetch_sensor_data(
            self,
            sensor_id: int,
            date_from: datetime,
            date_to: datetime = None
    ) -> list[views.SensorValueView]:
        # jeśli nie podano date_to, użyj teraz()
        if date_to is None:
            date_to = datetime.now()

        # pobierz zakres dostępny w bazie
        latest = self._database_client.fetch_latest_sensor_record_date(sensor_id)
        oldest = self._database_client.fetch_oldest_sensor_record_date(sensor_id)


        try:
            # jeśli brak w ogóle rekordów, pobierz cały przedział
            if latest is None or oldest is None:
                self.update_sensor_data(sensor_id, date_from, date_to)
            else:
                # jeśli date_to jest co najmniej o godzinę później niż latest
                if date_to.replace(minute=0,second=0,microsecond=0) != latest.replace(minute=0,second=0,microsecond=0):
                    self.update_sensor_data(sensor_id, max(date_from,latest), date_to)

                # jeśli date_from jest co najmniej o godzinę wcześniej niż oldest
                if date_from <= oldest - timedelta(hours=1):
                    self.update_sensor_data(sensor_id, date_from, min(date_to,oldest))
        except requests.exceptions.ConnectionError as e:
            logging.warning("Error while updating sensor data: %s", e)

        # w końcu zawsze zwracamy dane z bazy w zadanym przedziale
        return self._database_client.fetch_sensor_data(sensor_id, date_from, date_to)