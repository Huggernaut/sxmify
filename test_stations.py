from scraper import get_stations
try:
    stations = get_stations()
    print(f"Found {len(stations)} stations")
    if stations:
        print(f"First station: {stations[0]}")
except Exception as e:
    print(f"Error: {e}")
