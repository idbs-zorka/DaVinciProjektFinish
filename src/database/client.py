import os
import sqlite3
from datetime import datetime
from enum import Enum
from typing import Iterable, List, Optional

import src.api.models as api_models
import src.config as config
import src.database.views as views


OVERALL_SENSOR_TYPE_CODENAME: str = "Ogólny"


class Client:
    """
    Klient SQLite do:
      - inicjalizacji i migracji schematu,
      - przechowywania/aktualizacji danych o stacjach i sensorach,
      - odczytu widoków zdefiniowanych w src.database.views.
    """

    class GlobalUpdateIds(Enum):
        """Identyfikatory typów globalnych aktualizacji."""
        STATION_LIST = 0

    def __init__(self, database_filepath: str):
        """
        Inicjalizuje połączenie i ewentualnie wypełnia bazę.

        Args:
            database_filepath: ścieżka do pliku SQLite.
        """
        needs_populate = not os.path.exists(database_filepath)
        self._filepath = database_filepath
        self._conn = sqlite3.connect(database_filepath)
        self._conn.row_factory = sqlite3.Row
        self._cursor = self._conn.cursor()

        if needs_populate:
            self._populate_tables()

    def __del__(self):
        """Zamyka kursor i połączenie przy usunięciu instancji."""
        try:
            self._cursor.close()
            self._conn.close()
        except Exception:
            pass

    def duplicate_connection(self) -> 'Client':
        """Zwraca nową instancję Client na tym samym pliku bazy."""
        return Client(self._filepath)

    def _populate_tables(self) -> None:
        """Tworzy wszystkie tabele, triggery i dane początkowe."""
        # global_update
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_update (
                id INTEGER PRIMARY KEY,
                last_update_at INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._cursor.executemany(
            "INSERT OR IGNORE INTO global_update (id) VALUES (?)",
            [(member.value,) for member in self.GlobalUpdateIds]
        )

        # city, station, station_update
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS city (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                district TEXT NOT NULL,
                voivodeship TEXT NOT NULL,
                city TEXT NOT NULL UNIQUE
            )
        """)
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS station (
                id INTEGER PRIMARY KEY,
                codename TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                city_id INTEGER,
                address TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                FOREIGN KEY(city_id) REFERENCES city(id)
            )
        """)
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS station_update (
                station_id INTEGER UNIQUE,
                last_sensors_update_at INTEGER NOT NULL DEFAULT 0,
                last_indexes_update_at INTEGER NOT NULL DEFAULT 0,
                last_meta_update_at INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(station_id) REFERENCES station(id)
                    ON UPDATE CASCADE
            )
        """)
        # triggery dla station
        for evt in ("INSERT", "UPDATE"):
            self._cursor.execute(f"""
                CREATE TRIGGER IF NOT EXISTS tgr_on_{evt.lower()}_station
                AFTER {evt} ON station
                BEGIN
                    UPDATE global_update
                    SET last_update_at = unixepoch('now')
                    WHERE id = {self.GlobalUpdateIds.STATION_LIST.value};
                END
            """)

        # station_meta + triggery
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS station_meta (
                station_id INTEGER NOT NULL,
                international_codename TEXT NOT NULL,
                launch_date TEXT,
                shutdown_date TEXT,
                type TEXT,
                FOREIGN KEY(station_id) REFERENCES station(id)
                    ON UPDATE CASCADE
            )
        """)
        for evt in ("INSERT", "UPDATE"):
            self._cursor.execute(f"""
                CREATE TRIGGER IF NOT EXISTS tgr_on_{evt.lower()}_station_meta
                AFTER {evt} ON station_meta
                FOR EACH ROW
                BEGIN
                    INSERT OR REPLACE INTO station_update
                    (station_id, last_meta_update_at)
                    VALUES (NEW.station_id, unixepoch('now'));
                END
            """)

        # kategorie indeksów
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS aq_index_category_name (
                value INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        self._cursor.executemany(
            "INSERT OR IGNORE INTO aq_index_category_name (value, name) VALUES (?, ?)",
            ((v, n) for v, n in config.AQ_INDEX_CATEGORIES.items())
        )

        # typy sensorów
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_type (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codename TEXT NOT NULL UNIQUE
            )
        """)
        self._cursor.executemany(
            "INSERT OR IGNORE INTO sensor_type (codename) VALUES (?)",
            ((t,) for t in config.AQ_TYPES)
        )

        # aq_index + triggery
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS aq_index (
                station_id INTEGER,
                sensor_type_id INTEGER,
                value INTEGER,
                record_date TEXT,
                PRIMARY KEY(station_id, sensor_type_id),
                FOREIGN KEY(station_id) REFERENCES station(id)
                    ON UPDATE CASCADE,
                FOREIGN KEY(sensor_type_id) REFERENCES sensor_type(id),
                FOREIGN KEY(value) REFERENCES aq_index_category_name(value)
            )
        """)
        for evt in ("INSERT", "UPDATE"):
            self._cursor.execute(f"""
                CREATE TRIGGER IF NOT EXISTS tgr_on_{evt.lower()}_aq_index
                AFTER {evt} ON aq_index
                FOR EACH ROW
                BEGIN
                    INSERT INTO station_update
                      (station_id, last_indexes_update_at)
                    VALUES
                      (NEW.station_id, unixepoch('now'))
                    ON CONFLICT(station_id) DO UPDATE
                      SET last_indexes_update_at =
                        EXCLUDED.last_indexes_update_at;
                END
            """)

        # sensor + triggery
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor (
                id INTEGER PRIMARY KEY,
                station_id INTEGER,
                sensor_type_id INTEGER,
                FOREIGN KEY(station_id) REFERENCES station(id)
                    ON UPDATE CASCADE,
                FOREIGN KEY(sensor_type_id) REFERENCES sensor_type(id)
            )
        """)
        for evt in ("INSERT", "UPDATE"):
            self._cursor.execute(f"""
                CREATE TRIGGER IF NOT EXISTS tgr_on_{evt.lower()}_sensor
                AFTER {evt} ON sensor
                FOR EACH ROW
                BEGIN
                    INSERT INTO station_update
                      (station_id, last_sensors_update_at)
                    VALUES
                      (NEW.station_id, unixepoch('now'))
                    ON CONFLICT(station_id) DO UPDATE
                      SET last_sensors_update_at =
                        EXCLUDED.last_sensors_update_at;
                END
            """)

        # sensor_data
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                sensor_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                value REAL NOT NULL,
                PRIMARY KEY(sensor_id, date),
                FOREIGN KEY(sensor_id) REFERENCES sensor(id)
            )
        """)
        self._conn.commit()

    def update_stations(self, stations: Iterable[api_models.Station]) -> None:
        """
        Wstawia lub aktualizuje liste stacji i odpowiadające miasta.

        Args:
            stations: iterable obiektów Station z API.
        """
        # dodaj/ignoruj miasta
        city_params = ((s.district, s.voivodeship, s.city)
                       for s in stations)
        self._cursor.executemany(
            "INSERT OR IGNORE INTO city (district, voivodeship, city) VALUES (?, ?, ?)",
            city_params
        )
        # dodaj/aktualizuj stacje
        station_params = [
            {
                "id": s.id,
                "codename": s.codename,
                "name": s.name,
                "address": s.address,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "city": s.city
            }
            for s in stations
        ]
        self._cursor.executemany(
            """
            INSERT OR REPLACE INTO station
              (id, codename, name, city_id, address, latitude, longitude)
            SELECT
              :id, :codename, :name, city.id, :address, :latitude, :longitude
            FROM city WHERE city.city = :city
            """,
            station_params
        )
        self._conn.commit()

    def get_last_stations_update(self) -> datetime:
        """Zwraca czas ostatniej aktualizacji listy stacji."""
        row = self._cursor.execute(
            "SELECT last_update_at FROM global_update WHERE id = ?",
            (self.GlobalUpdateIds.STATION_LIST.value,)
        ).fetchone()
        return datetime.fromtimestamp(row["last_update_at"])

    def get_station_list_view(self) -> List[views.StationListView]:
        """Zwraca listę stacji (id, nazwa, współrzędne, miasto)."""
        rows = self._cursor.execute("""
            SELECT s.id, s.name, s.latitude, s.longitude, c.city
            FROM station AS s
            JOIN city AS c ON c.id = s.city_id
        """).fetchall()
        return [
            views.StationListView(
                id=r["id"],
                name=r["name"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                city=r["city"]
            ) for r in rows
        ]

    def update_station_meta(self, meta: List[api_models.StationMeta]) -> None:
        """
        Wstawia lub aktualizuje metadane stacji.

        Args:
            meta: lista obiektów StationMeta z API.
        """
        params = (
            {
                "station_id": m.codename,
                "international": m.international_codename,
                "launch_date": m.launch_date.isoformat(),
                "shutdown_date": m.close_date.isoformat(),
                "type": m.type
            } for m in meta
        )
        self._cursor.executemany(
            """
            INSERT OR REPLACE INTO station_meta
              (station_id, international_codename, launch_date, shutdown_date, type)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(p["station_id"], p["international"], p["launch_date"],
              p["shutdown_date"], p["type"]) for p in params]
        )
        self._conn.commit()

    def fetch_last_station_meta_update(self, station_id: int) -> datetime:
        """
        Zwraca datetime ostatniej aktualizacji metadanych stacji.

        Args:
            station_id: id stacji.
        """
        row = self._cursor.execute(
            "SELECT last_meta_update_at FROM station_update WHERE station_id = ?",
            (station_id,)
        ).fetchone()
        return datetime.fromtimestamp(row["last_meta_update_at"])

    def fetch_station_detail_view(
        self, station_id: int
    ) -> views.StationDetailsView:
        """
        Zwraca szczegóły wybranej stacji.

        Args:
            station_id: id stacji.
        """
        r = self._cursor.execute("""
            SELECT s.codename, s.name, c.district, c.voivodeship,
                   c.city, s.address
            FROM station AS s
            JOIN city AS c ON s.city_id = c.id
            WHERE s.id = ?
        """, (station_id,)).fetchone()
        return views.StationDetailsView(
            id=station_id,
            codename=r["codename"],
            name=r["name"],
            district=r["district"],
            voivodeship=r["voivodeship"],
            city=r["city"],
            address=r["address"]
        )

    def update_sensor_types(self, types: List[str]) -> None:
        """
        Dodaje typy sensorów.

        Args:
            types: lista kodów sensorów.
        """
        params = ((t,) for t in types)
        self._cursor.executemany(
            "INSERT OR IGNORE INTO sensor_type (codename) VALUES (?)",
            params
        )
        self._conn.commit()

    def update_station_air_quality_indexes(
        self, station_id: int, indexes: api_models.AirQualityIndexes
    ) -> None:
        """
        Wstawia lub aktualizuje indeksy jakości powietrza.

        Args:
            station_id: id stacji.
            indexes: obiekt z indeksem ogólnym i cząstkowym.
        """
        all_idxs = ((OVERALL_SENSOR_TYPE_CODENAME, indexes.overall),
                    *indexes.sensors.items())
        params = (
            {
                "station_id": station_id,
                "codename": key,
                "value": idx.value,
                "date": (idx.date.isoformat()
                         if idx.date else None)
            } for key, idx in all_idxs
        )
        self._cursor.executemany(
            """
            INSERT INTO aq_index
              (station_id, sensor_type_id, value, record_date)
            VALUES
              (
                :station_id,
                (SELECT id FROM sensor_type WHERE codename = :codename),
                :value,
                :date
              )
            ON CONFLICT(station_id, sensor_type_id) DO UPDATE
              SET value = EXCLUDED.value,
                  record_date = EXCLUDED.record_date
            """,
            params
        )
        self._conn.commit()

    def fetch_last_station_air_quality_indexes_update(
        self, station_id: int
    ) -> datetime:
        """
        Zwraca datetime ostatniej aktualizacji indeksów jakości powietrza.

        Args:
            station_id: id stacji.
        """
        row = self._cursor.execute(
            "SELECT last_indexes_update_at FROM station_update "
            "WHERE station_id = ?",
            (station_id,)
        ).fetchone()
        return (datetime.fromtimestamp(row["last_indexes_update_at"])
                if row else datetime.fromtimestamp(0))

    def fetch_station_air_quality_index_value(
        self, station_id: int, type_codename: str
    ) -> Optional[int]:
        """
        Zwraca wartość indeksu dla danego sensora.

        Args:
            station_id: id stacji.
            type_codename: kod sensora.
        """
        row = self._cursor.execute("""
            SELECT aq.value
            FROM aq_index AS aq
            JOIN sensor_type AS st
              ON aq.sensor_type_id = st.id
            WHERE aq.station_id = :sid
              AND st.codename = :cod
        """, {"sid": station_id, "cod": type_codename}).fetchone()
        return row["value"] if row else None

    def update_station_sensors(
        self, station_id: int, sensors: List[api_models.Sensor]
    ) -> None:
        """
        Wstawia nowe sensory do stacji.

        Args:
            station_id: id stacji.
            sensors: lista obiektów Sensor.
        """
        self.update_sensor_types([s.codename for s in sensors])
        params = (
            {
                "id": s.id,
                "station_id": station_id,
                "codename": s.codename
            } for s in sensors
        )
        self._cursor.executemany(
            """
            INSERT OR IGNORE INTO sensor
              (id, station_id, sensor_type_id)
            VALUES
              (
                :id,
                :station_id,
                (SELECT id FROM sensor_type WHERE codename = :codename)
              )
            """,
            params
        )
        self._conn.commit()

    def fetch_last_station_sensors_update(
        self, station_id: int
    ) -> datetime:
        """
        Zwraca datetime ostatniej aktualizacji sensorów.

        Args:
            station_id: id stacji.
        """
        row = self._cursor.execute(
            "SELECT last_sensors_update_at FROM station_update "
            "WHERE station_id = ?",
            (station_id,)
        ).fetchone()
        return (datetime.fromtimestamp(row["last_sensors_update_at"])
                if row else datetime.fromtimestamp(0))

    def fetch_station_sensors(
        self, station_id: int
    ) -> List[views.SensorView]:
        """
        Zwraca listę sensorów z kodami.

        Args:
            station_id: id stacji.
        """
        rows = self._cursor.execute("""
            SELECT s.id, st.codename
            FROM sensor AS s
            JOIN sensor_type AS st ON s.sensor_type_id = st.id
            WHERE s.station_id = ?
        """, (station_id,)).fetchall()
        return [
            views.SensorView(id=r["id"], codename=r["codename"])
            for r in rows
        ]

    def update_sensor_data(
        self, sensor_id: int, data: List[api_models.SensorData]
    ) -> None:
        """
        Wstawia lub aktualizuje pomiary z sensora.

        Args:
            sensor_id: id sensora.
            data: lista obiektów SensorData.
        """
        params = [
            (sensor_id, entry.date.isoformat(), entry.value)
            for entry in data
        ]
        self._cursor.executemany("""
            INSERT INTO sensor_data (sensor_id, date, value)
            VALUES (?, ?, ?)
            ON CONFLICT(sensor_id, date) DO UPDATE
              SET value = EXCLUDED.value
        """, params)
        self._conn.commit()

    def fetch_latest_sensor_record_date(
        self, sensor_id: int
    ) -> Optional[datetime]:
        """
        Zwraca datetime najnowszego rekordu sensora.

        Args:
            sensor_id: id sensora.
        """
        row = self._cursor.execute("""
            SELECT MAX(date) AS dt FROM sensor_data
            WHERE sensor_id = ?
        """, (sensor_id,)).fetchone()
        return (datetime.fromisoformat(row["dt"])
                if row and row["dt"] else None)

    def fetch_oldest_sensor_record_date(
        self, sensor_id: int
    ) -> Optional[datetime]:
        """
        Zwraca datetime najstarszego rekordu sensora.

        Args:
            sensor_id: id sensora.
        """
        row = self._cursor.execute("""
            SELECT MIN(date) AS dt FROM sensor_data
            WHERE sensor_id = ?
        """, (sensor_id,)).fetchone()
        return (datetime.fromisoformat(row["dt"])
                if row and row["dt"] else None)

    def fetch_sensor_data(
        self,
        sensor_id: int,
        date_from: datetime,
        date_to: datetime = datetime.now()
    ) -> List[views.SensorValueView]:
        """
        Zwraca pomiary sensora z zakresu dat.

        Args:
            sensor_id: id sensora.
            date_from: początek zakresu.
            date_to: koniec zakresu (domyślnie teraz).
        """
        rows = self._cursor.execute("""
            SELECT date, value FROM sensor_data
            WHERE sensor_id = :sid
              AND date >= :dfrom
              AND date <= :dto
        """, {
            "sid": sensor_id,
            "dfrom": date_from.isoformat(),
            "dto": date_to.isoformat()
        }).fetchall()
        return [
            views.SensorValueView(
                date=datetime.fromisoformat(r["date"]),
                value=r["value"]
            ) for r in rows
        ]

