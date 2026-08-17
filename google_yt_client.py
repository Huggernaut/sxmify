import os
import datetime
import re
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from ytmusicapi import YTMusic

# Google API Scopes for YouTube Data API
SCOPES = ['https://www.googleapis.com/auth/youtube']

def get_google_auth_flow(redirect_uri):
    # Use environment variables
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError("Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET")
    
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    return flow

def search_track_google(yt, title, artist):
    query = f"{title} {artist}"
    try:
        results = yt.search(query, filter="songs", limit=1)
        if results:
            return results[0].get('videoId')
    except Exception as e:
        print(f"Error searching for {query} on YTMusic API: {e}")
    return None

def create_playlist_and_add_tracks_google(credentials_dict, track_details, station_id="unknown", scrape_type="recent", days=None, station_name=None, custom_name=None, cumulative=False):
    """
    Creates a playlist via YouTube Data API and adds tracks.
    track_details should be a list of dicts: [{'title': '...', 'artist': '...', 'id': '...'}]
    """
    credentials = Credentials(**credentials_dict)
    youtube = build('youtube', 'v3', credentials=credentials)
    
    if custom_name:
        playlist_name = custom_name
    else:
        if station_name:
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
    
    existing_playlist_id = None
    
    print(f"Searching for existing playlist '{playlist_name}' (Google API)...")
    try:
        # Get user's playlists
        request = youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50
        )
        response = request.execute()
        playlists = response.get('items', [])
        for pl in playlists:
            if pl['snippet']['title'] == playlist_name:
                existing_playlist_id = pl['id']
                break
    except Exception as e:
        print(f"Error fetching playlists (Google API): {e}")
        
    if existing_playlist_id and not cumulative:
        print(f"Found existing playlist '{playlist_name}'. Recreating...")
        try:
            youtube.playlists().delete(id=existing_playlist_id).execute()
        except Exception as e:
            print(f"Error deleting playlist: {e}")
        existing_playlist_id = None
        
    if not existing_playlist_id:
        print(f"Creating new playlist '{playlist_name}'...")
        try:
            request = youtube.playlists().insert(
                part="snippet,status",
                body={
                  "snippet": {
                    "title": playlist_name,
                    "description": description
                  },
                  "status": {
                    "privacyStatus": "public"
                  }
                }
            )
            response = request.execute()
            existing_playlist_id = response['id']
        except Exception as e:
            print(f"Error creating playlist: {e}")
            return None

    # Resolve video IDs and add them
    video_ids = []
    yt = YTMusic()
    
    from concurrent.futures import ThreadPoolExecutor
    
    def search_worker(track):
        return search_track_google(yt, track['title'], track['artist'])
        
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(search_worker, track_details)
        for res in results:
            if res:
                video_ids.append(res)

    if video_ids:
        print(f"Adding {len(video_ids)} tracks to playlist {existing_playlist_id}...")
        for i, vid in enumerate(video_ids):
            try:
                body = {
                    "snippet": {
                        "playlistId": existing_playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": vid
                        }
                    }
                }
                
                if cumulative:
                    body["snippet"]["position"] = i
                
                request = youtube.playlistItems().insert(
                    part="snippet",
                    body=body
                )
                request.execute()
            except HttpError as e:
                # 409 means duplicate in some contexts, but usually fine
                print(f"Error adding video {vid}: {e}")
                
    return f"https://music.youtube.com/playlist?list={existing_playlist_id}"
