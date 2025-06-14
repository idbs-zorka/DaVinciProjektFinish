from PySide6.QtCore import QDateTime
from datetime import datetime

def qt_to_datetime(dt: QDateTime) -> datetime:
    ms = dt.toMSecsSinceEpoch()
    return datetime.fromtimestamp(ms / 1000.0)

def datetime_to_qt(dt: datetime) -> QDateTime:
    ms = int(dt.timestamp() * 1000)
    return QDateTime.fromMSecsSinceEpoch(ms)
