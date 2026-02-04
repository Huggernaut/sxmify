# Sxmify

A Python web application that scrapes song history from **xmplaylist.com** and automatically exports the tracks to a new **Spotify** playlist. Built out of equal frustration with Spotify for their incredibly repetitive algos and Sirius for closing my "Trust me bro, I'm a dealership and we just sold this car; please refresh its trial" loophole.

Built to support all stations available on xmplaylist.com (there might be some funkiness with stations that begin with a number). Possibly adding support for something other than Spotify in the future, but that would involve making an Apple account or actually using Amazon Music.

## Features

*   **Web Scraper**: Extracts song data (Artist, Title, Spotify Link) from live playlist pages using `cloudscraper` and `BeautifulSoup`.
*   **Spotify Integration**: Authenticates users securely via Spotify OAuth and creates playlists on their behalf.
*   **Web Interface**: A clean, dark-mode Flask web app to easily run the tool from a browser.
*   **Multiple Scrape Modes**: Support for "Recently Played", "Newest Additions", and "Most Heard" (with customizable timeframes).
*   **Custom Playlist Naming**: Option to set custom names for exported playlists or use the default `XM: [Station] - [Mode]` format.

## Tech Stack

*   **Python 3.x**
*   **Flask** (Web Framework)
*   **Spotipy** (Spotify Web API Wrapper)
*   **CloudScraper** (Bypass Cloudflare protection)
*   **BeautifulSoup4** (HTML Parsing)
*   **CSS3** (Custom Styling)

## License
MIT License - see [LICENSE](LICENSE) for details.
