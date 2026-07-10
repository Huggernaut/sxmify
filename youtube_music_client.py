import os
import re
import datetime
from ytmusicapi import YTMusic
from base_client import BaseStreamingClient

class YouTubeMusicClient(BaseStreamingClient):
    def __init__(self, auth_file="oauth.json"):
        # The auth_file could be either oauth.json or headers_auth.json
        # Check if file exists, else try to use environment variable
        
        self.auth_file = auth_file
        
        if os.environ.get("YTMUSIC_OAUTH"):
            # Write to a temporary oauth.json if it comes from env var (e.g. Vercel)
            import tempfile
            self.auth_file = os.path.join(tempfile.gettempdir(), "oauth.json")
            with open(self.auth_file, "w") as f:
                f.write(os.environ.get("YTMUSIC_OAUTH"))
            
        try:
            self.yt = YTMusic(self.auth_file)
        except Exception as e:
            print(f"Warning: Failed to initialize YTMusic: {e}")
            self.yt = None

    def search_track(self, title, artist):
        if not self.yt:
            return None
        
        query = f"{title} {artist}"
        try:
            search_results = self.yt.search(query, filter="songs", limit=1)
            if search_results:
                return search_results[0].get('videoId')
        except Exception as e:
            print(f"Error searching for {query} on YouTube Music: {e}")
        return None

    def create_playlist_and_add_tracks(self, track_ids, station_id="unknown", scrape_type="recent", days=None, station_name=None, custom_name=None, cumulative=False):
        if not self.yt or not track_ids:
            return None
            
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
        
        print(f"Searching for existing playlist '{playlist_name}'...")
        try:
            playlists = self.yt.get_library_playlists(limit=100)
            for pl in playlists:
                if pl.get('title') == playlist_name:
                    existing_playlist_id = pl.get('playlistId')
                    break
        except Exception as e:
            print(f"Error fetching YT Music playlists: {e}")
            
        if existing_playlist_id and cumulative:
            print(f"Found existing playlist '{playlist_name}' and cumulative mode is enabled.")
            # YTMusic API does not make it easy to deduplicate by ID without fetching all tracks
            # We will just append the tracks. We could fetch existing and dedupe if we wanted.
            try:
                # Deduplication logic (optional but good)
                pl_details = self.yt.get_playlist(existing_playlist_id, limit=None)
                existing_video_ids = set([t.get('videoId') for t in pl_details.get('tracks', [])])
                
                new_track_ids = [tid for tid in track_ids if tid not in existing_video_ids]
                if new_track_ids:
                    print(f"Adding {len(new_track_ids)} new tracks to YT Music cumulative playlist...")
                    self.yt.add_playlist_items(existing_playlist_id, new_track_ids)
                else:
                    print("No new tracks to add.")
            except Exception as e:
                print(f"Error adding to existing playlist: {e}")
                
            return f"https://music.youtube.com/playlist?list={existing_playlist_id}"
            
        else:
            if existing_playlist_id:
                print(f"Found existing playlist '{playlist_name}'. Updating...")
                # YTMusic doesn't have a direct 'replace' method, so we delete existing tracks and add new ones,
                # or delete the playlist and recreate. Recreating is safer/faster.
                self.yt.delete_playlist(existing_playlist_id)
            
            print(f"Creating new playlist '{playlist_name}'...")
            try:
                playlist_id = self.yt.create_playlist(playlist_name, description, privacy_status="PUBLIC", video_ids=track_ids)
                if type(playlist_id) == str:
                    print("Successfully created YouTube Music playlist!")
                    return f"https://music.youtube.com/playlist?list={playlist_id}"
                else:
                    print(f"Unexpected response creating playlist: {playlist_id}")
            except Exception as e:
                print(f"Error creating YT Music playlist: {e}")
                
        return None
