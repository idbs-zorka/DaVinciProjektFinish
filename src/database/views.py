"""
Objekty przechowujące dane z bazy danych
"""


from datetime import datetime
from dataclasses import dataclass

@dataclass
class StationCommonView:
    id: int

@dataclass
class StationListView(StationCommonView):
    name: str
    latitude: float
    longitude: float
    city: str

@dataclass
class AQIndexView:
    codename: str
    value: int
    category: str

@dataclass
class SensorView:
    id: int
    codename: str

@dataclass
class StationDetailsView(StationCommonView):
    codename: str
    name: str
    district: str
    voivodeship: str
    city: str
    address: str

@dataclass
class SensorValueView:
    date: datetime
    value: float