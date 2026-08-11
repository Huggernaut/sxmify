import os
import datetime
from flask import Flask, request, url_for, session, redirect, render_template
from dotenv import load_dotenv
from scraper import scrape_tracks, get_stations
from google_yt_client import get_google_auth_flow, create_playlist_and_add_tracks_google
from youtube_music_client import YouTubeMusicClient
import googleapiclient.discovery
from google.oauth2.credentials import Credentials

load_dotenv(override=True)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def filter_blacklisted_tracks(tracks, blacklist_items):
    if not blacklist_items or not tracks:
        return tracks
    # Filter case-insensitively on artist and title
    return [
        t for t in tracks 
        if not any(
            b.strip().lower() in t['artist'].lower() or 
            b.strip().lower() in t['title'].lower() 
            for b in blacklist_items if b.strip()
        )
    ]

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    # Use a secure random key if not provided (note: sessions will reset on app restart)
    app.secret_key = os.urandom(24)
app.config['SESSION_COOKIE_NAME'] = 'yt-login-session'

# Configuration
raw_redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/callback")
if not raw_redirect_uri.startswith("http"):
    GOOGLE_REDIRECT_URI = f"https://{raw_redirect_uri}"
else:
    GOOGLE_REDIRECT_URI = raw_redirect_uri
# User must update Dashboard to this URI or use the one they configured.


@app.route('/')
def index():
    stations = get_stations()
    is_logged_in = session.get('google_credentials') is not None
    user_display_name = session.get('user_display_name') if is_logged_in else None
    user_image_url = session.get('user_image_url') if is_logged_in else None
        
    return render_template('index.html', stations=stations, 
                           is_logged_in=is_logged_in,
                           user_display_name=user_display_name,
                           user_image_url=user_image_url)

@app.route('/login')
def login():
    flow = get_google_auth_flow(GOOGLE_REDIRECT_URI)
    auth_url, state = flow.authorization_url(prompt='consent select_account', access_type='offline')
    
    session['oauth_state'] = state
    if hasattr(flow, 'code_verifier'):
        session['code_verifier'] = flow.code_verifier
    
    if request.args.get('next') == 'review':
        session['return_to_review'] = True
    elif request.args.get('next') == 'bulk':
        session['return_to_bulk'] = True
    elif request.args.get('next') == 'token':
        session['return_to_token'] = True
        
    return redirect(auth_url)

@app.route('/callback')
def callback():
    return_to_review = session.get('return_to_review')
    last_scrape = session.get('last_scrape')
    return_to_bulk = session.get('return_to_bulk')
    return_to_token = session.get('return_to_token')
    
    code = request.args.get('code')
    try:
        flow = get_google_auth_flow(GOOGLE_REDIRECT_URI)
        if 'code_verifier' in session:
            flow.code_verifier = session['code_verifier']
        flow.fetch_token(code=code)
        credentials = flow.credentials
        session['google_credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
    except Exception as e:
        return render_template('index.html', error=f"Google Authentication Error: {e}", stations=get_stations())
    
    try:
        youtube = googleapiclient.discovery.build('youtube', 'v3', credentials=credentials)
        channels_response = youtube.channels().list(mine=True, part='snippet').execute()
        items = channels_response.get('items', [])
        if items:
            snippet = items[0]['snippet']
            session['user_display_name'] = snippet.get('title')
            thumbnails = snippet.get('thumbnails', {})
            if 'default' in thumbnails:
                session['user_image_url'] = thumbnails['default']['url']
    except Exception as e:
        pass

    if session.get('return_to_review') and session.get('last_scrape'):
         session.pop('return_to_review', None)
         return redirect(url_for('show_review'))
    
    if session.get('return_to_bulk'):
        session.pop('return_to_bulk', None)
        return redirect(url_for('bulk_select'))
        
    if session.get('return_to_token'):
        session.pop('return_to_token', None)
        return redirect(url_for('show_token'))

    pending_export = session.get('pending_export')
    if pending_export:
        return finish_export(pending_export)
        
    return redirect(url_for('index'))

@app.route('/scrape', methods=['POST'])
def scrape():
    base_url = request.form.get('url')
    station_name = request.form.get('station_name')
    scrape_type = request.form.get('scrape_type', 'recent')
    days = request.form.get('days', '7')
    limit = int(request.form.get('limit', 100))

    session['last_scrape'] = {
        'url': base_url,
        'station_name': station_name,
        'scrape_type': scrape_type,
        'days': days,
        'limit': limit
    }

    print(f"DEBUG: base_url='{base_url}', scrape_type='{scrape_type}', days='{days}', limit={limit}")

    if not base_url:
        return render_template('index.html', error="Please select a station.", stations=get_stations(), user_display_name=session.get('user_display_name'))
    
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
        return render_template('index.html', error="No tracks found on that page.", stations=get_stations(), user_display_name=session.get('user_display_name'))

    station_id = "unknown"
    try:
        parts = target_url.rstrip('/').split('/')
        if 'station' in parts:
            station_id = parts[parts.index('station') + 1]
    except Exception:
        pass

    is_logged_in = session.get('google_credentials') is not None
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

    print(f"Re-Scraping {target_url} (limit={limit})...")
    tracks = scrape_tracks(target_url, limit=limit)
    
    station_id = "unknown"
    try:
        parts = target_url.rstrip('/').split('/')
        if 'station' in parts:
            station_id = parts[parts.index('station') + 1]
    except Exception:
        pass
        
    is_logged_in = session.get('google_credentials') is not None
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
    track_ids = request.form.getlist('track_ids')
    station_id = request.form.get('station_id', 'unknown')
    station_name = request.form.get('station_name')
    custom_name = request.form.get('custom_name')
    scrape_type = request.form.get('scrape_type', 'recent')
    days = request.form.get('days', None)
    reverse_order = request.form.get('reverse_order')
    cumulative = request.form.get('cumulative') == 'true'
    platform = request.form.get('platform', 'ytmusic') # Changed default to ytmusic
    
    if reverse_order:
         track_ids.reverse()

    track_details = []
    for tid in track_ids:
        title = request.form.get(f'track_titles_{tid}')
        artist = request.form.get(f'track_artists_{tid}')
        if title and artist:
            track_details.append({'id': tid, 'title': title, 'artist': artist})

    export_data = {
        'track_ids': track_ids,
        'track_details': track_details,
        'station_id': station_id,
        'station_name': station_name,
        'custom_name': custom_name,
        'scrape_type': scrape_type,
        'days': days,
        'cumulative': cumulative,
        'platform': platform
    }

    if platform == 'ytmusic_personal':
        if not session.get('google_credentials'):
            session['pending_export'] = export_data
            return redirect(url_for('login'))
        return finish_export(export_data)
        
    elif platform == 'ytmusic':
        return finish_export(export_data)

def finish_export(export_data):
    """Helper to actually create the playlist"""
    track_ids = export_data.get('track_ids')
    track_details = export_data.get('track_details', [])
    station_id = export_data.get('station_id')
    station_name = export_data.get('station_name')
    custom_name = export_data.get('custom_name')
    scrape_type = export_data.get('scrape_type', 'recent')
    days = export_data.get('days')
    cumulative = export_data.get('cumulative', False)
    platform = export_data.get('platform', 'ytmusic')
    
    print(f"Starting export for {len(track_ids)} tracks to {platform}...")
    
    if not track_ids:
        return redirect(url_for('index'))
        
    if platform == 'ytmusic_personal':
        try:
            credentials_dict = session.get('google_credentials')
            playlist_url = create_playlist_and_add_tracks_google(
                credentials_dict, track_details, station_id, scrape_type, days, station_name, custom_name, cumulative=cumulative
            )
            if playlist_url:
                session.pop('pending_export', None)
                return render_template('success.html', playlist_url=playlist_url, count=len(track_ids))
            else:
                return render_template('index.html', error="Failed to create playlist on Google API.", stations=get_stations())
        except Exception as e:
             return render_template('index.html', error=f"Google API Error: {e}", stations=get_stations())
             
    elif platform == 'ytmusic':
        try:
            yt_client = YouTubeMusicClient()
            if not yt_client.yt:
                return render_template('index.html', error="YouTube Music OAuth is not configured properly on the server.", stations=get_stations())
                
            yt_track_ids = []
            from concurrent.futures import ThreadPoolExecutor
            
            def search_worker(track):
                return yt_client.search_track(track['title'], track['artist'])
                
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = executor.map(search_worker, track_details)
                for res in results:
                    if res:
                        yt_track_ids.append(res)
            
            if not yt_track_ids:
                return render_template('index.html', error="Could not find any of the requested tracks on YouTube Music.", stations=get_stations())
                
            playlist_url = yt_client.create_playlist_and_add_tracks(
                yt_track_ids, station_id, scrape_type, days, station_name, custom_name, cumulative=cumulative
            )
            
            session.pop('pending_export', None)
            return render_template('success.html', playlist_url=playlist_url, count=len(yt_track_ids))
            
        except Exception as e:
            return render_template('index.html', error=f"YouTube Music Error: {e}", stations=get_stations())

@app.route('/bulk')
def bulk_select():
    stations = get_stations()
    
    saved_data = session.get('saved_bulk_data', {})
    selected_urls = saved_data.get('station_urls', [])
    selected_scrape_type = saved_data.get('scrape_type', 'recent')
    selected_days = saved_data.get('days', '7')
    
    is_logged_in = session.get('google_credentials') is not None
    user_display_name = session.get('user_display_name') if is_logged_in else None
    user_image_url = session.get('user_image_url') if is_logged_in else None
    
    return render_template('bulk.html', 
                           stations=stations,
                           selected_urls=selected_urls,
                           selected_scrape_type=selected_scrape_type,
                           selected_days=selected_days,
                           is_logged_in=is_logged_in,
                           user_display_name=user_display_name,
                           user_image_url=user_image_url)

@app.route('/bulk_export', methods=['POST'])
def bulk_export():
    station_urls = request.form.getlist('station_urls')
    scrape_type = request.form.get('scrape_type', 'recent')
    days = request.form.get('days', '7')
    limit = 100 
    cumulative = request.form.get('cumulative') == 'true'
    platform = request.form.get('platform', 'ytmusic')
    
    blacklist_param = request.form.get('blacklist')
    blacklist_items = [b.strip() for b in blacklist_param.split(',')] if blacklist_param else None

    if platform == 'ytmusic_personal':
        if not session.get('google_credentials'):
            session['saved_bulk_data'] = {
                'station_urls': station_urls,
                'scrape_type': scrape_type,
                'days': days,
                'cumulative': cumulative,
                'blacklist': blacklist_param
            }
            return redirect(url_for('login', next='bulk'))

    session.pop('saved_bulk_data', None) 
    
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
                 
             tracks = filter_blacklisted_tracks(tracks, blacklist_items)
             
             if not tracks:
                 res['error'] = "All tracks filtered out by blacklist"
                 results.append(res)
                 continue
                 
             res['track_count'] = len(tracks)
             
             station_id = "unknown"
             try:
                parts = url.rstrip('/').split('/')
                if 'station' in parts:
                    station_id = parts[parts.index('station') + 1]
             except:
                 pass

             if platform == 'ytmusic_personal':
                 credentials_dict = session.get('google_credentials')
                 playlist_url = create_playlist_and_add_tracks_google(
                     credentials_dict, tracks, station_id, scrape_type, days, station_name, cumulative=cumulative
                 )
             else:
                 yt_client = YouTubeMusicClient()
                 yt_track_ids = []
                 from concurrent.futures import ThreadPoolExecutor
                 
                 def search_worker(track):
                     return yt_client.search_track(track['title'], track['artist'])
                     
                 with ThreadPoolExecutor(max_workers=10) as executor:
                     search_results = executor.map(search_worker, tracks)
                     for res in search_results:
                         if res:
                             yt_track_ids.append(res)
                 playlist_url = yt_client.create_playlist_and_add_tracks(
                     yt_track_ids, station_id, scrape_type, days, station_name, cumulative=cumulative
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

@app.route('/token')
def show_token():
    return redirect(url_for('index'))

@app.route('/api/cron/update')
def cron_update():
    auth_header = request.headers.get('Authorization')
    expected_secret = os.environ.get('CRON_SECRET')
    
    if not expected_secret or auth_header != f"Bearer {expected_secret}":
        return {"error": "Unauthorized"}, 401
    
    stations_param = request.args.get('stations')
    if stations_param:
        station_ids = [s.strip() for s in stations_param.split(',')]
    else:
         station_id = request.args.get('station', 'factionpunk')
         station_ids = [station_id]
         
    cumulative_param = request.args.get('cumulative')
    cumulative = cumulative_param in ['true', '1']
    
    blacklist_param = request.args.get('blacklist')
    blacklist_items = [b.strip() for b in blacklist_param.split(',')] if blacklist_param else None
    
    # Use personal auth for cron if available, fallback to bot account
    try:
        if os.environ.get("YTMUSIC_OAUTH_PERSONAL"):
            yt_client = YouTubeMusicClient(env_var="YTMUSIC_OAUTH_PERSONAL")
        else:
            yt_client = YouTubeMusicClient()
            
        if not yt_client.yt:
            return {"error": "Missing YTMUSIC_OAUTH_PERSONAL or YTMUSIC_OAUTH env"}, 500
        
        all_stations = get_stations()
        results = []
        
        for input_sid in station_ids:
             try:
                 sid = input_sid
                 resolved_name = None
                 input_lower = input_sid.lower()
                 
                 for s in all_stations:
                     s_id = str(s.get('id', '')).lower()
                     s_num = str(s.get('number', '')).lower()
                     if s_num == '9999': s_num = ''
                     s_name = str(s.get('name', '')).lower()
                     s_name_no_num = s_name.split(' - ', 1)[-1] if ' - ' in s_name else s_name
                     
                     if input_lower in (s_id, s_num, s_name_no_num, s_name_no_num.replace(' ', ''), s_name):
                         sid = s.get('id')
                         resolved_name = s.get('name')
                         break
                         
                 url = f"https://xmplaylist.com/station/{sid}"
                 tracks = scrape_tracks(url, limit=100)
                 
                 if not tracks:
                      results.append({"station": input_sid, "error": f"No tracks found for station {input_sid}"})
                      continue
                      
                 tracks = filter_blacklisted_tracks(tracks, blacklist_items)
                 
                 if not tracks:
                      results.append({"station": input_sid, "error": f"All tracks were filtered out by blacklist for station {input_sid}"})
                      continue
                 
                 if resolved_name:
                     station_name = resolved_name
                 else:
                     station_url_suffix = f"/station/{sid}"
                     station_name = next((s['name'] for s in all_stations if s['url'].endswith(station_url_suffix)), sid.replace('-', ' ').title())
                 
                 yt_track_ids = []
                 from concurrent.futures import ThreadPoolExecutor
                 
                 def search_worker(track):
                     return yt_client.search_track(track['title'], track['artist'])
                     
                 with ThreadPoolExecutor(max_workers=10) as executor:
                     search_results = executor.map(search_worker, tracks)
                     for res in search_results:
                         if res:
                             yt_track_ids.append(res)
                 
                 playlist_url = yt_client.create_playlist_and_add_tracks(
                     yt_track_ids, sid, 'recent', None, station_name, cumulative=cumulative
                 )
                 
                 results.append({
                     "success": True, 
                     "station": station_name,
                     "playlist_url": playlist_url, 
                     "tracks_added": len(yt_track_ids)
                 })
             except Exception as inner_e:
                 import traceback
                 traceback.print_exc()
                 results.append({"station": input_sid, "error": str(inner_e)})
                 
        return {"results": results}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
