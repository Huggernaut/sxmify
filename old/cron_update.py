import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from scraper import scrape_tracks
from spotify_client import create_playlist_and_add_tracks

# Load environment variables
load_dotenv()

def main():
    print("Starting Cron Job: Playlist Update")
    
    # 1. Configuration
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:5000/callback")
    refresh_token = os.environ.get("SPOTIPY_REFRESH_TOKEN")
    
    station_id = os.environ.get("TARGET_STATION_ID", "factionpunk") # Default or Env
    
    if not all([client_id, client_secret, refresh_token]):
        print("Error: Missing required environment variables (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)")
        return

    # 2. Authenticate using Refresh Token
    print("Authenticating with Refresh Token...")
    sp_oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="playlist-modify-public playlist-modify-private"
    )
    
    token_info = sp_oauth.refresh_access_token(refresh_token)
    
    if not token_info:
        print("Error: Failed to refresh access token.")
        return
        
    sp = spotipy.Spotify(auth=token_info['access_token'])
    print(f"Authenticated as: {sp.current_user()['display_name']}")

    # 3. Scrape Tracks
    target_url = f"https://xmplaylist.com/station/{station_id}"
    print(f"Scraping station: {station_id} ({target_url})...")
    
    # Default to "recent" tracks
    tracks = scrape_tracks(target_url, limit=50)
    
    if not tracks:
        print("No tracks found. Aborting update.")
        return
        
    print(f"Found {len(tracks)} tracks.")
    track_ids = [t['id'] for t in tracks]

    # 4. Update Playlist
    print("Updating Spotify Playlist...")
    # Note: You can customize scrape_type/days here if you want "Newest" or "Most Heard" logic
    # checking for custom name env var
    custom_name = os.environ.get("TARGET_PLAYLIST_NAME") 
    
    playlist_url = create_playlist_and_add_tracks(
        sp, 
        track_ids, 
        station_id=station_id,
        scrape_type="recent", # Default to recent stream
        station_name=None,    # Let it autosource or use ID
        custom_name=custom_name
    )
    
    if playlist_url:
        print(f"Success! Playlist updated: {playlist_url}")
    else:
        print("Failed to update playlist.")

if __name__ == "__main__":
    main()
