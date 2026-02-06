# Sxmify 🎵

A Python web application that scrapes song history from **xmplaylist.com** and automatically exports the tracks to a new **Spotify** playlist.

Built for the Faction Punk station, but adaptable to others.

## 🚀 Features

*   **Web Scraper**: Extracts song data (Artist, Title, Spotify Link) from live playlist pages using `BeautifulSoup`.
*   **Spotify Integration**: Authenticates users securely via Spotify OAuth and creates playlists on their behalf.
*   **Web Interface**: A clean, dark-mode Flask web app to easily run the tool from a browser.

## 🛠️ Tech Stack

*   **Python 3.x**
*   **Flask** (Web Framework)
*   **Spotipy** (Spotify Web API Wrapper)
*   **BeautifulSoup4** (HTML Parsing)
*   **CSS3** (Custom Styling)

## 📦 Installation & Usage

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/sxmify.git
cd sxmify
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Spotify App
1.  Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
2.  Create a new app.
3.  Add `http://127.0.0.1:5000/callback` to the **Redirect URIs**.
4.  Copy your **Client ID** and **Client Secret**.

### 4. Configuration
Create a `.env` file in the root directory:
```env
SPOTIPY_CLIENT_ID=your_client_id
SPOTIPY_CLIENT_SECRET=your_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:5000/callback
FLASK_SECRET_KEY=supersecretkey
```

### 5. Run Locally
```bash
flask run
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## ☁️ Deployment

This project includes a `Procfile` for easy deployment on platforms like **Render** or **Heroku**.

1.  Push code to GitHub.
2.  Connect repository to your hosting provider.
3.  Set the environment variables in the hosting dashboard.
4.  Update the **Redirect URI** in Spotify Dashboard to your production URL (e.g., `https://your-app.onrender.com/callback`).

## 📄 License
MIT License - see [LICENSE](LICENSE) for details.
