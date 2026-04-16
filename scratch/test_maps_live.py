import googlemaps
from app.config import settings

def test_maps_live():
    if not settings.maps_api_key:
        print("Error: MAPS_API_KEY not set in .env")
        return
    
    print(f"Testing Google Maps API Key: {settings.maps_api_key[:10]}...")
    gmaps = googlemaps.Client(key=settings.maps_api_key)
    
    # Test coordinates (Bangalore mock locations)
    origin = (12.9716, 77.5946)  # Gate A
    dest = (12.9718, 77.5965)    # Main Stadium
    
    try:
        result = gmaps.distance_matrix(origins=[origin], destinations=[dest], mode="walking")
        status = result["rows"][0]["elements"][0]["status"]
        if status == "OK":
            distance = result["rows"][0]["elements"][0]["distance"]["text"]
            print(f"Success! Walking distance: {distance}")
        else:
            print(f"API Error: {status}")
            print(f"Full response: {result}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_maps_live()
