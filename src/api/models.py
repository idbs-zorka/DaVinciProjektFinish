"""
Objekty przechowujące dane z API
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Station:
    id: int
    codename: str
    name: str
    district: str
    voivodeship: str
    city: str
    address: str
    latitude: float
    longitude: float

@dataclass
class StationMeta:
    codename: str
    international_codename: str | None
    launch_date: datetime
    close_date: datetime | None
    type: str

@dataclass
class IndexCategory:
    value: int
    name: str

@dataclass
class Index:
    date: datetime | None
    value: int | None

@dataclass
class AirQualityIndexes:
    overall: Index
    sensors: dict[str,Index]
    index_status: bool | None
    index_critical: str | None

@dataclass
class Sensor:
    id: int
    codename: str
    name: str

@dataclass
class SensorData:
    date: datetime
    value: float