from abc import ABC, abstractmethod

class BaseStreamingClient(ABC):
    @abstractmethod
    def search_track(self, title, artist):
        """
        Search for a track by title and artist.
        Returns the track ID for the platform, or None if not found.
        """
        pass

    @abstractmethod
    def create_playlist_and_add_tracks(self, track_ids, station_id="unknown", scrape_type="recent", days=None, station_name=None, custom_name=None, cumulative=False):
        """
        Create a new playlist (or update an existing one) and add the given tracks.
        Returns the playlist URL or ID.
        """
        pass
