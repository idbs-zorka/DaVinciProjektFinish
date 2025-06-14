from geopy import Nominatim
from geopy.distance import distance
import geocoder

def find_position(location_name: str) -> tuple[float,float]:
    locator = Nominatim(user_agent="DaVinci Project - Test")
    location = locator.geocode(location_name,exactly_one=True)
    return location.latitude, location.longitude

def current_location() -> tuple[float,float]:
    return geocoder.ip('me').latlng
