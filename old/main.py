import os
import getpass
from dotenv import load_dotenv
from scraper import scrape_tracks
from spotify_client import get_spotify_client, create_playlist_and_add_tracks

load_dotenv()

def main():
    print("--- XM Playlist to Spotify Exporter ---")
    
    # Scrape
    url = input("Enter XM Playlist URL: ").strip()
    if not url:
        print("URL is required.")
        return
        
    # Extract station_id
    station_id = "unknown"
    try:
        parts = url.rstrip('/').split('/')
        if 'station' in parts:
            station_id = parts[parts.index('station') + 1]
    except Exception:
        pass
        
    print("Scraping...")
    tracks = scrape_tracks(url)
    track_ids = [t['id'] for t in tracks if 'id' in t]
    
    if not track_ids:
        print("No tracks found.")
        return
        
    print(f"Found {len(track_ids)} tracks.")
    
    # Authenticate
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
        
    if not client_id or not client_secret:
        print("Error: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env")
        return

    # Export
    try:
        sp = get_spotify_client(client_id, client_secret)
        playlist_url = create_playlist_and_add_tracks(sp, track_ids, station_id)
        print(f"Success! Playlist: {playlist_url}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
