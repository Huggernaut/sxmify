import re
import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth

def get_spotify_client(client_id, client_secret):
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8888/callback",
        scope="playlist-modify-public playlist-modify-private"
    ))

def create_playlist_and_add_tracks(sp, track_ids, station_id="unknown", scrape_type="recent", days=None, station_name=None, custom_name=None):
    # Creates or updates a playlist for the given station
    if not track_ids:
        return None
        
    user_id = sp.current_user()['id']
    
    if custom_name:
        playlist_name = custom_name
    else:
        # Construct descriptive name
        if station_name:
            # Remove leading numbers (e.g. "34 - Lithium" -> "Lithium")
            name_suffix = re.sub(r'^\d+\s+-\s+', '', station_name)
        else:
            name_suffix = station_id.replace('-', ' ').title() if station_id != "unknown" else "Unknown Station"
        
        if scrape_type == 'newest':
            playlist_name = f"XM: {name_suffix} - Newest Additions"
        elif scrape_type == 'most_heard':
            timeframe = f" ({days} Days)" if days else ""
            playlist_name = f"XM: {name_suffix} - Most Played {timeframe}"
        else:
             playlist_name = f"XM: {name_suffix} - Recently Played"
    
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    description = f"Last updated: {date_str}"
    
    # Search for existing playlist
    playlist_id = None
    playlist_url = None
    
    print(f"Searching for existing playlist '{playlist_name}'...")
    try:
        results = sp.current_user_playlists(limit=50)
        for item in results['items']:
            if item['name'] == playlist_name:
                playlist_id = item['id']
                playlist_url = item['external_urls']['spotify']
                break
    except Exception as e:
        print(f"Warning: Could not search playlists: {e}")

    if playlist_id:
        print(f"Found existing playlist. Updating tracks and description...")
        sp.playlist_change_details(playlist_id, description=description)
    else:
        print(f"Creating new playlist '{playlist_name}'...")
        playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=True, description=description)
        playlist_id = playlist['id']
        playlist_url = playlist['external_urls']['spotify']
    
    # Spotify API limit for adding tracks is 100
    track_uris = [f"spotify:track:{tid}" for tid in track_ids]
    batch_size = 100
    
    print(f"Syncing {len(track_uris)} tracks to playlist...")
    
    # First batch uses replace to clear old tracks if updating
    first_batch = track_uris[:batch_size]
    sp.playlist_replace_items(playlist_id, first_batch)
    print(f"Batch 1 processed")
    

    for i in range(batch_size, len(track_uris), batch_size):
        batch = track_uris[i:i + batch_size]
        sp.playlist_add_items(playlist_id, batch)
        print(f"Batch {i//batch_size + 1} added")
        
    print(f"Done! Playlist URL: {playlist_url}")
    return playlist_url
