import os
import datetime
from flask import Flask, request, url_for, session, redirect, render_template
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from scraper import scrape_tracks, get_stations
from spotify_client import create_playlist_and_add_tracks

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'

# Configuration
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:5000/callback") 
# User must update Dashboard to this URI or use the one they configured.

def create_spotify_oauth():
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
    return redirect(auth_url)

@app.route('/callback')
def callback():
    sp_oauth = create_spotify_oauth()
    
    # Preserve pending export before clearing session
    pending_export = session.get('pending_export')
    
    session.clear()
    
    # Restore pending export
    if pending_export:
        session['pending_export'] = pending_export

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

    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/token')
def show_token():
    token_info = session.get('token_info')
    if not token_info:
        return redirect(url_for('login'))
        
    refresh_token = token_info.get('refresh_token')
    
    return f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 2rem auto; padding: 1rem; border: 1px solid #ccc; border-radius: 8px;">
        <h2>Setup Automatic Updates</h2>
        <p>To enable the background Cron Job, you need to add this <strong>Refresh Token</strong> to your Render Environment Variables.</p>
        <hr>
        <p><strong>SPOTIPY_REFRESH_TOKEN</strong></p>
        <textarea style="width: 100%; height: 100px; font-family: monospace;">{refresh_token}</textarea>
        <p><em>Copy the entire string above.</em></p>
        <hr>
        <p><a href="/">Back to Home</a></p>
    </div>
    """



if __name__ == "__main__":
    app.run(debug=True)
