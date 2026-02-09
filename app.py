import os
import datetime
from flask import Flask, request, url_for, session, redirect, render_template
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from scraper import scrape_tracks, get_stations
from spotify_client import create_playlist_and_add_tracks

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'

# Configuration
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI", "https://localhost:5000/callback") 
# User must update Dashboard to this URI or use the one they configured.

def create_spotify_oauth():
    print(f"DEBUG: Using Redirect URI: {SPOTIPY_REDIRECT_URI}")
    return SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope="playlist-modify-public playlist-modify-private"
    )

@app.route('/')
def index():
    stations = get_stations()
    # Pass user info if logged in
    user_display_name = None
    if session.get('token_info'):
        user_display_name = session.get('user_display_name')
        
    return render_template('index.html', stations=stations, user_display_name=user_display_name)

@app.route('/login')
def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    
    # Check if we should return to review page
    if request.args.get('next') == 'review':
        session['return_to_review'] = True
    elif request.args.get('next') == 'bulk':
        session['return_to_bulk'] = True
        
    return redirect(auth_url)

@app.route('/callback')
def callback():
    sp_oauth = create_spotify_oauth()
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    
    # Get user info for display
    try:
        sp = spotipy.Spotify(auth=token_info['access_token'])
        current_user = sp.current_user()
        session['user_display_name'] = current_user.get('display_name')
        if current_user.get('images'):
            session['user_image_url'] = current_user['images'][0]['url']
    except:
        pass

    # Check for return to review page
    if session.get('return_to_review') and session.get('last_scrape'):
         session.pop('return_to_review', None)
         return redirect(url_for('show_review'))
    
    if session.get('return_to_bulk'):
        session.pop('return_to_bulk', None)
        return redirect(url_for('bulk_select'))

    # Check for pending export
    pending_export = session.get('pending_export')
    if pending_export:
        return finish_export(token_info, pending_export)
        
    return redirect(url_for('index'))

@app.route('/scrape', methods=['POST'])
def scrape():
    # Authentication check intentionally skipped to allow guest scraping
    
    # Check token expiration IF logged in (just cleanup)
    token_info = session.get('token_info', None)
    if token_info:
        sp_oauth = create_spotify_oauth()
        if sp_oauth.is_token_expired(token_info):
            print("Token expired. Refreshing...")
            token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
            session['token_info'] = token_info
    
    base_url = request.form.get('url')
    station_name = request.form.get('station_name')
    scrape_type = request.form.get('scrape_type', 'recent')
    days = request.form.get('days', '7')
    limit = int(request.form.get('limit', 100))

    # Store in session for potential return after login
    session['last_scrape'] = {
        'url': base_url,
        'station_name': station_name,
        'scrape_type': scrape_type,
        'days': days,
        'limit': limit
    }

    print(f"DEBUG: base_url='{base_url}', scrape_type='{scrape_type}', days='{days}', limit={limit}")

    if not base_url:
        return render_template('index.html', error="Please select a station.")
    
    # Clean base_url
    base_url = base_url.rstrip('/')

    target_url = base_url
    scrape_description = "Tracks" # Default
    
    if scrape_type == 'newest':
        target_url = f"{base_url}/newest"
        scrape_description = "Newest Additions"
    elif scrape_type == 'most_heard':
        target_url = f"{base_url}/most-heard?days={days}"
        scrape_description = f"Most Played (Last {days} Days)"
    elif scrape_type == 'recent':
        scrape_description = "Recently Played"

    print(f"Scraping {target_url} (limit={limit})...")
    tracks = scrape_tracks(target_url, limit=limit)
    
    if not tracks:
        return render_template('index.html', error="No tracks found on that page.")

    # Extract station_id from URL
    station_id = "unknown"
    try:
        parts = target_url.rstrip('/').split('/')
        if 'station' in parts:
            station_id = parts[parts.index('station') + 1]
    except Exception:
        pass

    # Render Review Page
    # Pass login status so view knows whether to say "Export" or "Login & Export"
    is_logged_in = session.get('token_info') is not None
    user_display_name = session.get('user_display_name')
    user_image_url = session.get('user_image_url')

    return render_template('review.html', 
                           tracks=tracks, 
                           target_url=target_url, 
                           station_id=station_id, 
                           station_name=station_name,
                           scrape_description=scrape_description,
                           is_logged_in=is_logged_in,
                           user_display_name=user_display_name,
                           user_image_url=user_image_url)


@app.route('/review')
def show_review():
    """Display review page using session data (for redirects after login)"""
    last_scrape = session.get('last_scrape')
    if not last_scrape:
        return redirect(url_for('index'))
    
    # Re-use variables
    base_url = last_scrape.get('url')
    station_name = last_scrape.get('station_name')
    scrape_type = last_scrape.get('scrape_type')
    days = last_scrape.get('days')
    limit = last_scrape.get('limit')
    
    # Logic duplication from scrape() - cleaner refactor would be to extract this
    # but for now, keep it simple.
    
    if not base_url:
        return redirect(url_for('index'))
        
    base_url = base_url.rstrip('/')
    target_url = base_url
    scrape_description = "Tracks" 
    
    if scrape_type == 'newest':
        target_url = f"{base_url}/newest"
        scrape_description = "Newest Additions"
    elif scrape_type == 'most_heard':
        target_url = f"{base_url}/most-heard?days={days}"
        scrape_description = f"Most Played (Last {days} Days)"
    elif scrape_type == 'recent':
        scrape_description = "Recently Played"

    # Don't re-scrape if we can avoid it? 
    # Actually we should re-scrape to be safe and simple, or store tracks in session (too big?)
    # Re-scraping is safer for state.
    
    print(f"Re-Scraping {target_url} (limit={limit})...")
    tracks = scrape_tracks(target_url, limit=limit)
    
    station_id = "unknown"
    try:
        parts = target_url.rstrip('/').split('/')
        if 'station' in parts:
            station_id = parts[parts.index('station') + 1]
    except Exception:
        pass
        
    is_logged_in = session.get('token_info') is not None
    user_display_name = session.get('user_display_name')
    user_image_url = session.get('user_image_url')

    return render_template('review.html', 
                            tracks=tracks, 
                            target_url=target_url, 
                            station_id=station_id, 
                            station_name=station_name,
                            scrape_description=scrape_description,
                            is_logged_in=is_logged_in,
                            user_display_name=user_display_name,
                            user_image_url=user_image_url)


@app.route('/export', methods=['POST'])
def export():
    # Gather form data
    track_ids = request.form.getlist('track_ids')
    station_id = request.form.get('station_id', 'unknown')
    station_name = request.form.get('station_name')
    custom_name = request.form.get('custom_name')
    scrape_type = request.form.get('scrape_type', 'recent')
    days = request.form.get('days', None)
    reverse_order = request.form.get('reverse_order')
    
    if reverse_order:
         track_ids.reverse()

    export_data = {
        'track_ids': track_ids,
        'station_id': station_id,
        'station_name': station_name,
        'custom_name': custom_name,
        'scrape_type': scrape_type,
        'days': days
    }

    # Check if logged in
    token_info = session.get('token_info', None)
    if not token_info:
        # Not logged in? Save intent and redirect to login
        session['pending_export'] = export_data
        return redirect(url_for('login'))

    # Check token expiration
    sp_oauth = create_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        print("Token expired (export). Refreshing...")
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info
        
    return finish_export(token_info, export_data)

def finish_export(token_info, export_data):
    """Helper to actually create the playlist"""
    track_ids = export_data.get('track_ids')
    station_id = export_data.get('station_id')
    station_name = export_data.get('station_name')
    custom_name = export_data.get('custom_name')
    scrape_type = export_data.get('scrape_type', 'recent')
    days = export_data.get('days')
    
    print(f"Starting export for {len(track_ids)} tracks...")
    
    if not track_ids:
        return redirect(url_for('index'))
        
    # Create Playlist
    sp = spotipy.Spotify(auth=token_info['access_token'])
    try:
        playlist_url = create_playlist_and_add_tracks(sp, track_ids, station_id, scrape_type, days, station_name, custom_name)
        print(f"Playlist created successfully: {playlist_url}")
        
        # Clear pending if successful
        session.pop('pending_export', None)
        
        return render_template('success.html', playlist_url=playlist_url, count=len(track_ids))
    except spotipy.exceptions.SpotifyException as e:
         return render_template('index.html', error=f"Spotify Error: {e}")

@app.route('/bulk')
def bulk_select():
    stations = get_stations()
    return render_template('bulk.html', stations=stations)

@app.route('/bulk_export', methods=['POST'])
def bulk_export():
    # Check login
    token_info = session.get('token_info', None)
    if not token_info:
        return redirect(url_for('login', next='bulk'))

    sp_oauth = create_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info

    sp = spotipy.Spotify(auth=token_info['access_token'])

    station_urls = request.form.getlist('station_urls')
    scrape_type = request.form.get('scrape_type', 'recent')
    days = request.form.get('days', '7')
    limit = 100 
    
    # Pre-fetch stations for name lookup
    all_stations = get_stations()
    station_map = {s['url']: s['name'] for s in all_stations}
    
    results = []
    print(f"Starting bulk update for {len(station_urls)} stations...")
    
    for url in station_urls:
         station_name = station_map.get(url, "Unknown Station")
         
         res = {
             'station_name': station_name,
             'success': False,
             'track_count': 0,
             'playlist_url': None,
             'error': None
         }
         
         try:
             # 1. Scrape
             target_url = url
             if scrape_type == 'newest':
                 target_url = f"{url}/newest"
             elif scrape_type == 'most_heard':
                 target_url = f"{url}/most-heard?days={days}"
             
             print(f"Bulk scraping: {target_url}")
             tracks = scrape_tracks(target_url, limit=limit)
             
             if not tracks:
                 res['error'] = "No tracks found"
                 results.append(res)
                 continue
                 
             track_ids = [t['id'] for t in tracks]
             res['track_count'] = len(track_ids)
             
             # 2. Extract station_id for naming
             station_id = "unknown"
             try:
                parts = url.rstrip('/').split('/')
                if 'station' in parts:
                    station_id = parts[parts.index('station') + 1]
             except:
                 pass

             # 3. Create Playlist
             playlist_url = create_playlist_and_add_tracks(
                 sp, track_ids, station_id, scrape_type, days, station_name
             )
             
             res['success'] = True
             res['playlist_url'] = playlist_url
             
         except Exception as e:
             print(f"Error processing {station_name}: {e}")
             res['error'] = str(e)
             
         results.append(res)
         
    return render_template('bulk_results.html', results=results)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/debug')
def debug_info():
    import os
    import json
    import sys
    
    info = []
    info.append(f"Python Version: {sys.version}")
    info.append(f"CWD: {os.getcwd()}")
    
    # Check directory listing
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        info.append(f"Script Dir: {current_dir}")
        files = os.listdir(current_dir)
        info.append(f"Files in Dir: {files}")
        
        json_path = os.path.join(current_dir, 'stations.json')
        info.append(f"stations.json exists: {os.path.exists(json_path)}")
        if os.path.exists(json_path):
             info.append(f"stations.json size: {os.path.getsize(json_path)} bytes")

    except Exception as e:
        info.append(f"File Error: {e}")
        
    # check stations
    try:
        from scraper import get_stations
        stations = get_stations()
        info.append(f"Station Count: {len(stations)}")
        if stations:
            info.append(f"Sample: {stations[0]}")
    except Exception as e:
        info.append(f"Station Error: {e}")

    # check scraping tracks
    try:
        from scraper import scrape_tracks
        # Test with SiriusXM Hits 1 (usually has data)
        info.append("<br><strong>Testing Track Scrape (SiriusXM Hits 1)...</strong>")
        tracks = scrape_tracks("https://xmplaylist.com/station/siriusxmhits1", limit=10)
        info.append(f"Tracks Found: {len(tracks)}")
        if tracks:
            info.append(f"Sample Track: {tracks[0]}")
        else:
            info.append("No tracks found, likely blocked or empty.")
            
    except Exception as e:
        info.append(f"Track Scrape Error: {e}")

    # Raw API Test
    try:
        import cloudscraper
        import html
        url = "https://xmplaylist.com/api/station/siriusxmhits1"
        info.append(f"<br><strong>Raw API Test ({url}) with CloudScraper...</strong>")
        
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url)
        info.append(f"Status Code: {resp.status_code}")
        
        text = resp.text
        # Preview content (escape HTML to prevent rendering if it's a block page)
        preview = html.escape(text[:1000])
        info.append(f"Response Preview: {preview}")
    except Exception as e:
        info.append(f"Raw Request Error: {e}")
        
    return "<br>".join(info)

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, ssl_context='adhoc')
