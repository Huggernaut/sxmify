from scraper import scrape_tracks
try:
    # Test with a known station URL
    url = "https://xmplaylist.com/station/siriusxmhits1"
    print(f"Testing track scrape for {url}...")
    tracks = scrape_tracks(url, limit=5)
    print(f"Found {len(tracks)} tracks")
    if tracks:
        print(f"First track: {tracks[0]}")
    else:
        print("No tracks returned.")
except Exception as e:
    print(f"Error: {e}")
