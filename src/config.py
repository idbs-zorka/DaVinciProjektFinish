from datetime import timedelta

UPDATE_INTERVALS = {
    "station": timedelta(days=1),
    "aq_indexes": timedelta(hours=1),
    "sensors": timedelta(days=1)
}

AQ_INDEX_CATEGORIES = {
    -1: "Brak wartości",
    0: "Bardzo dobry",
    1: "Dobry",
    2: "Umiarkowany",
    3: "Zły",
    4: "Bardzo zły",
}

AQ_INDEX_CATEGORIES_COLORS = {
    -1: 0xA9A9A9,  # Brak indeksu – ciemny szary
     0: 0x009966,  # Bardzo dobry – ciemna zieleń
     1: 0x66CC66,  # Dobry – jasna zieleń
     2: 0xFFDE33,  # Umiarkowany – żółć
     3: 0xFF9933,  # Zły – pomarańcz
     4: 0xCC0033,  # Bardzo zły – czerwień
}


AQ_TYPES = [
    "Ogólny",
    "SO2",
    "NO2",
    "PM10",
    "PM2.5",
    "O3"
]