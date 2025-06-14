import logging
import typing
from datetime import datetime
from typing import Callable, Any

import requests

import src.api.exceptions as exceptions
import src.api.models as models
from src.api.exceptions import APIError, TooManyRequests


class Client:
    """
    Klient HTTP dla API GIOŚ (https://api.gios.gov.pl),
    obsługujący paginację, obsługę błędów oraz mapowanie odpowiedzi na modele.
    Przechowuje również status połączenia z API oraz udostępnia callback sygnalizujący zmiane stanu.
    """

    __BASE = "https://api.gios.gov.pl"
    _connection_status: bool = True
    connection_status_changed : typing.Callable[[bool],None] = None

    @property
    def connection_status(self):
        return self._connection_status

    @connection_status.setter
    def connection_status(self,value: bool):
        """Setter statusu połączenia, w razie zmiany wywołuje callback oraz zapisuje wartość"""
        if self._connection_status == value:
            return

        self._connection_status = value
        if self.connection_status_changed is not None:
            self.connection_status_changed(value)

    def make_url(
        self,
        endpoint: str,
        page: int = 0,
        size: int = 100,
        args: dict[str, Any] = None,
    ) -> str:
        """
        Buduje pełny URL z bazowego adresu, ścieżki oraz parametrów paginacji i dodatkowych argumentów.

        Args:
            endpoint (str): Ścieżka API (np. "pjp-api/v1/rest/station/findAll").
            page (int, opcjonalnie): Numer strony (0-based). Domyślnie 0.
            size (int, opcjonalnie): Liczba rekordów na stronę. Domyślnie 100.
            args (dict[str, Any], opcjonalnie): Dodatkowe parametry query string.

        Returns:
            str: Pełny adres URL gotowy do wywołania przez requests.get().
        """
        if args is None:
            args = {}
        url = f"{self.__BASE}/{endpoint}?page={page}&size={size}"
        for key, value in args.items():
            url += f"&{key}={value}"
        return url

    def _get(
        self,
        endpoint: str,
        page: int = 0,
        size: int = 100,
        args: dict[str, Any] = None,
    ) -> Any:
        """
        Wykonuje żądanie GET, sprawdza status odpowiedzi i zwraca dane z JSON.

        Args:
            endpoint (str): Ścieżka API.
            page (int, opcjonalnie): Numer strony.
            size (int, opcjonalnie): Rozmiar strony.
            args (dict[str, Any], opcjonalnie): Dodatkowe parametry query string.

        Returns:
            Any: Zdeserializowany obiekt JSON (słownik lub lista).

        Raises:
            exceptions.APIError: W przypadku błędu HTTP z mapowaniem pól error_code, error_reason,
                error_result oraz error_solution udostępnionymi przez GIOŚ API.
        """
        try:
            url = self.make_url(endpoint, page, size, args)
            logging.info(f"API Request: {url}")
            response = requests.get(url, timeout=None)
            self.connection_status = True
            response.raise_for_status()
            logging.info(f"API Request finished!")
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"API Request error!")
            payload = http_err.response.json()
            raise exceptions.APIError(
                code=payload.get("error_code"),
                reason=payload.get("error_reason"),
                result=payload.get("error_result"),
                solution=payload.get("error_solution"),
            )
        except requests.exceptions.ConnectionError as conn_err:
            self.connection_status = False
            raise conn_err

    def _get_collected(
        self,
        endpoint: str,
        target: str,
        size: int = 100,
        args: dict[str, Any] = None,
    ) -> typing.Union[list, dict]:
        """
        Pobiera wszystkie strony wyników (paginacja) i scala dane z klucza target.

        Args:
            endpoint (str): Ścieżka API.
            target (str): Klucz w JSON, pod którym znajdują się dane (lista lub słownik).
            args (dict[str, Any], opcjonalnie): Dodatkowe parametry query string.

        Returns:
            list|dict: Scalona lista lub słownik wyników.

        Raises:
            TypeError: Gdy zwrócony fragment JSON nie jest listą ani słownikiem.
        """
        response = self._get(endpoint, size=size, args=args)
        total_pages = int(response.get("totalPages", 1))
        fragment = response.get(target)

        if isinstance(fragment, list):
            result = list(fragment)
        elif isinstance(fragment, dict):
            result = dict(fragment)
        else:
            raise TypeError(f"Nieoczekiwany typ danych: {type(fragment).__name__}")

        for page in range(1, total_pages):
            response = self._get(endpoint, page=page, args=args)
            fragment = response.get(target)
            if isinstance(fragment, list):
                result.extend(fragment)
            elif isinstance(fragment, dict):
                result.update(fragment)
            else:
                raise TypeError(f"Nieoczekiwany typ danych: {type(fragment).__name__}")

        return result

    def _get_each(
        self,
        endpoint: str,
        target: str,
        callback: Callable[[Any], None],
        size: int = 500, # Maksymalna wielkość API
        args: dict[str, Any] = None,
    ) -> None:
        """
        Iteruje po wszystkich stronach wyników i wywołuje funkcję callback dla każdego fragmentu target.

        Args:
            endpoint (str): Ścieżka API.
            target (str): Klucz JSON, z którego pobierane są fragmenty danych.
            callback (Callable[[Any], None]): Funkcja przetwarzająca fragment danych.
            size (int, opcjonalnie): Liczba rekordów na stronę. Domyślnie 500.
            args (dict[str, Any], opcjonalnie): Dodatkowe parametry query string.
        """
        response = self._get(endpoint, size=size, args=args)
        total_pages = int(response.get("totalPages", 1))

        for page in range(total_pages):
            if page > 0:
                response = self._get(endpoint, page=page, args=args)
            callback(response.get(target))

    def fetch_stations(self) -> list[models.Station]:
        """
        Pobiera pełną listę stacji pomiarowych.

        Returns:
            list[models.Station]: Lista obiektów Station z danymi lokalizacyjnymi i nazewnictwem.
        """
        raw = self._get_collected(
            endpoint="pjp-api/v1/rest/station/findAll",
            target="Lista stacji pomiarowych",
        )
        return [
            models.Station(
                id=entry["Identyfikator stacji"],
                codename=entry["Kod stacji"],
                name=entry["Nazwa stacji"],
                district=entry["Powiat"],
                voivodeship=entry["Województwo"],
                city=entry["Nazwa miasta"],
                address=entry["Ulica"],
                latitude=entry["WGS84 φ N"],
                longitude=entry["WGS84 λ E"],
            )
            for entry in raw
        ]

    def fetch_station_meta(
        self,
        city: str = None,
        station_codename: str = None,
    ) -> list[models.StationMeta]:
        """
        Pobiera metadane stacji pomiarowych z opcjonalnym filtrowaniem.

        Args:
            city (str, opcjonalnie): Nazwa miasta do filtrowania.
            station_codename (str, opcjonalnie): Kod stacji do filtrowania.

        Returns:
            list[models.StationMeta]: Lista obiektów StationMeta.
        """
        params: dict[str, Any] = {}
        if city:
            params["filter[miasto]"] = city
        if station_codename:
            params["filter[kod-stacji]"] = station_codename

        raw = self._get_collected(
            endpoint="pjp-api/v1/rest/metadata/stations",
            target="Lista metadanych stacji pomiarowych",
            args=params,
        )
        return [
            models.StationMeta(
                codename=entry["Kod stacji"],
                international_codename=entry["Kod międzynarodowy"],
                launch_date=datetime.fromisoformat(entry["Data uruchomienia"]),
                close_date=(
                    datetime.fromisoformat(entry["Data zamknięcia"])
                    if entry.get("Data zamknięcia")
                    else None
                ),
                type=entry["Rodzaj stacji"],
            )
            for entry in raw
        ]

    def fetch_air_quality_indexes(
        self,
        station_id: int,
    ) -> models.AirQualityIndexes:
        """
        Pobiera aktualne indeksy jakości powietrza dla danej stacji.

        Args:
            station_id (int): Identyfikator stacji pomiarowej.

        Returns:
            models.AirQualityIndexes: Obiekt zawierający indeks ogólny i dla poszczególnych wskaźników.

        Raises:
            ValueError: Gdy odpowiedź API ma niespodziewany format.
        """
        raw = self._get_collected(
            endpoint=f"pjp-api/v1/rest/aqindex/getIndex/{station_id}",
            target="AqIndex",
        )

        def parse_date(key: str) -> typing.Optional[datetime]:
            value = raw.get(key)
            return datetime.fromisoformat(value) if value else None

        overall = models.Index(
            date=parse_date("Data wykonania obliczeń indeksu"),
            value=raw.get("Wartość indeksu"),
        )
        sensors: dict[str, models.Index] = {}
        for pollutant in ["NO2", "O3", "PM10", "PM2.5", "SO2"]:
            sensors[pollutant] = models.Index(
                date=parse_date(f"Data wykonania obliczeń indeksu dla wskaźnika {pollutant}"),
                value=raw.get(f"Wartość indeksu dla wskaźnika {pollutant}"),
            )

        return models.AirQualityIndexes(
            overall=overall,
            sensors=sensors,
            index_status=raw.get("Status indeksu ogólnego dla stacji pomiarowej"),
            index_critical=raw.get("Kod zanieczyszczenia krytycznego"),
        )

    def fetch_station_sensors(self, station_id: int) -> list[models.Sensor]:
        """
        Pobiera listę sensorów dostępnych na danej stacji.

        Args:
            station_id (int): Identyfikator stacji pomiarowej.

        Returns:
            list[models.Sensor]: Lista obiektów Sensor z identyfikatorem i nazwą wskaźnika.
        """
        raw = self._get_collected(
            endpoint=f"pjp-api/v1/rest/station/sensors/{station_id}",
            target="Lista stanowisk pomiarowych dla podanej stacji",
        )
        return [
            models.Sensor(
                id=entry["Identyfikator stanowiska"],
                codename=entry["Wskaźnik - kod"],
                name=entry["Wskaźnik"],
            )
            for entry in raw
        ]

    def fetch_sensor_data(self, sensor_id: int) -> list[models.SensorData]:
        """
        Pobiera bieżące dane pomiarowe dla czujnika, iterując po wszystkich stronach.

        Args:
            sensor_id (int): Identyfikator czujnika.

        Returns:
            list[models.SensorData]: Lista obiektów SensorData z datą i wartością pomiaru.
        """
        result: list[models.SensorData] = []

        def collect(data: list[dict[str, Any]]) -> None:
            for entry in data:
                value = entry.get("Wartość")
                if value is not None:
                    result.append(
                        models.SensorData(
                            date=datetime.fromisoformat(entry["Data"]),
                            value=value,
                        )
                    )

        self._get_each(
            endpoint=f"pjp-api/v1/rest/data/getData/{sensor_id}",
            target="Lista danych pomiarowych",
            callback=collect,
        )
        return result

    def fetch_sensor_archival_data(
        self,
        sensor_id: int,
        date_from: datetime = None,
        date_to: datetime = None,
        days: int = None,
    ) -> list[models.SensorData]:
        """
        Pobiera archiwalne dane pomiarowe dla czujnika z opcjonalnym zakresem czasowym.

        Args:
            sensor_id (int): Identyfikator czujnika.
            date_from (datetime, opcjonalnie): Data początkowa.
            date_to (datetime, opcjonalnie): Data końcowa.
            days (int, opcjonalnie): Liczba dni do pobrania przed dniem dzisiejszym.

        Returns:
            list[models.SensorData]: Lista obiektów SensorData z datą i wartością.
        """
        result: list[models.SensorData] = []
        params: dict[str, Any] = {}
        date_format = "%Y-%m-%d %H:%M"

        if date_from:
            params["dateFrom"] = date_from.strftime(date_format)
        if date_to:
            params["dateTo"] = date_to.strftime(date_format)
        if days:
            params["dayNumber"] = days

        def collect(data: list[dict[str, Any]]) -> None:
            for entry in data:
                result.append(
                    models.SensorData(
                        date=datetime.fromisoformat(entry["Data"]),
                        value=entry.get("Wartość"),
                    )
                )

        try:
            self._get_each(
                endpoint=f"pjp-api/v1/rest/archivalData/getDataBySensor/{sensor_id}",
                target="Lista archiwalnych wyników pomiarów",
                callback=collect,
                args=params,
            )
        except APIError as e:
            match e.code:
                case "API-ERR-100003":
                    raise TooManyRequests(
                        "API rate limit exceeded (max 2 requests per minute). "
                        "Please wait before retrying the request."
                    )
        return result
