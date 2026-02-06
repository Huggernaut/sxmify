from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import json
import os

from urllib.parse import urlparse, parse_qs

def load_fallback_stations():
    try:
        path = os.path.join(os.path.dirname(__file__), 'stations.json')
        print(f"Loading fallback stations from {path}...")
        with open(path, 'r', encoding='utf-8') as f:
            stations = json.load(f)
            print(f"Loaded {len(stations)} stations from fallback.")
            return stations
    except Exception as e:
        print(f"Error loading fallback: {e}")
        return []

def get_stations():
    # Scrape the station list from xmplaylist.com/station
    url = "https://xmplaylist.com/station"
    try:
        print(f"Fetching stations from {url}...")
        response = requests.get(url, impersonate="chrome")
        print(f"Station Fetch Status: {response.status_code}")
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching stations: {e}")
        return load_fallback_stations()

    soup = BeautifulSoup(response.text, 'html.parser')
    stations = []
    
    # Filter valid station links
    links = soup.find_all('a', href=re.compile(r'^/station/[a-zA-Z0-9]+$'))
    
    for link in links:
        href = link.get('href')
        name = link.text.strip()
        station_id = href.split('/')[-1]
        
        # Simple dedupe based on ID
        if not any(s['id'] == station_id for s in stations):
            stations.append({
                'name': name,
                'url': f"https://xmplaylist.com{href}",
                'id': station_id
            })
            
    filtered_stations = []

    for station in stations:
        match = re.match(r'^(\d+)(.*)', station['name'])
        
        # Handle decades (e.g., 770s -> 7, 70s)
        decade_match = re.match(r'^(\d)(\d0)(s\s.*)', station['name'])
        
        # Handle concatenated decades (e.g., 7140s -> 71 - 40s)
        concat_decade_match = re.match(r'^(\d+)(00s|10s|20s|30s|40s|50s|60s|70s|80s|90s|2k|Pop2K)(.*)', station['name'], re.IGNORECASE)

        if decade_match:
             station['number'] = int(decade_match.group(1))
             station['display_name'] = f"{decade_match.group(1)} - {decade_match.group(2)}{decade_match.group(3)}"
             
        elif concat_decade_match:
             station['number'] = int(concat_decade_match.group(1))
             station['display_name'] = f"{concat_decade_match.group(1)} - {concat_decade_match.group(2)}{concat_decade_match.group(3)}"
             
        elif match and int(match.group(1)) <= 999:
            station['number'] = int(match.group(1))
            station['display_name'] = f"{match.group(1)} - {match.group(2).strip()}"
        else:
            station['number'] = 9999 # Put non-numbered at the end
            station['display_name'] = station['name']
            
        filtered_stations.append(station)

    filtered_stations.sort(key=lambda x: (x['number'], x['name']))
    
    # Update name to display name for frontend
    for s in filtered_stations:
        s['name'] = s['display_name']
        
    if not filtered_stations:
        print("No stations found after scraping. Using fallback.")
        return load_fallback_stations()

    return filtered_stations

def fetch_from_api(station_id, mode, days=None, limit=60):
    base_api = f"https://xmplaylist.com/api/station/{station_id}"
    
    if mode == 'newest':
        url = f"{base_api}/newest"
        return fetch_all_results(url, limit)
    elif mode == 'most_heard':
        url = f"{base_api}/most-heard"
        params = {}
        if days:
            params['days'] = days
        return fetch_all_results(url, limit, params)
    else:
        return fetch_paged_results(base_api, limit)

def fetch_all_results(url, limit, params=None):
    print(f"API Fetch: {url} params={params}")
    try:
        resp = requests.get(url, params=params, impersonate="chrome")
        if resp.status_code != 200:
            print(f"API Error {resp.status_code}")
            return []
        
        data = resp.json()
        results = data.get('results', [])
        if not results and isinstance(data, list):
            results = data
            
        return process_api_results(results[:limit])
    except Exception as e:
        print(f"API Exception: {e}")
        return []

def fetch_paged_results(url, target_count):
    all_tracks = []
    next_url = url
    
    while next_url and len(all_tracks) < target_count:
        print(f"Fetching Page: {next_url}")
        try:
            resp = requests.get(next_url, impersonate="chrome")
            if resp.status_code != 200:
                break
            
            data = resp.json()
            results = data.get('results', [])
            all_tracks.extend(process_api_results(results))
            
            next_url = data.get('next')
            # Fix next url if it's http
            if next_url and next_url.startswith('http:'):
                next_url = next_url.replace('http:', 'https:')
                
        except Exception as e:
            print(f"Pagination Error: {e}")
            break
            
    return all_tracks[:target_count]

def process_api_results(results):
    tracks = []
    for item in results:
        try:
            spotify_id = item.get('spotify', {}).get('id')
            if not spotify_id:
                continue
                
            track_obj = item.get('track', {})
            title = track_obj.get('title')
            artists = track_obj.get('artists', [])
            artist = artists[0] if artists else "Unknown"
            

                 
            image_url = item.get('spotify', {}).get('albumImageSmall')
            if not image_url:
                 image_url = item.get('spotify', {}).get('albumImageMedium')

            tracks.append({
                'id': spotify_id,
                'title': title,
                'artist': artist,

                'image_url': image_url,
                'spotify_url': f"https://open.spotify.com/track/{spotify_id}"
            })
        except Exception as e:
            continue
    return tracks

def scrape_tracks(url, limit=60):
    print(f"Scraping {url} with limit {limit}...")
    
    # Parse URL to determine mode and station
    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')    
    if len(path_parts) >= 2 and path_parts[0] == 'station':
        station_id = path_parts[1]
        mode = 'recent'
        days = None
        
        if len(path_parts) > 2:
            if path_parts[2] == 'newest':
                mode = 'newest'
            elif path_parts[2] == 'most-heard':
                mode = 'most_heard'
                qs = parse_qs(parsed.query)
                days = qs.get('days', [None])[0]
        
        print(f"Detected Station: {station_id}, Mode: {mode}, Days: {days}")
        return fetch_from_api(station_id, mode, days, limit)

    print("URL pattern not recognized. Returning empty.")
    return []
