import os
import json
import webbrowser
import http.client
import threading
import difflib
from yandex_music import Client
import config
from config import TOKEN_FILE

http.client._encode = lambda x: x.encode('utf-8')

class YandexAPI:
    def __init__(self, root, logger_func, on_code_cb=None, on_success_cb=None):
        self.root = root
        self.client = Client()
        self.is_authorized = False
        self.is_authorizing = False
        self.logger = logger_func
        self.on_code_cb = on_code_cb
        self.on_success_cb = on_success_cb

    def check_token_at_startup(self):
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
                    access_token = token_data.get('access_token')
                self.client = Client(access_token).init()
                self.client.account_status()
                self.is_authorized = True
                self.logger(config.tr("token_valid"), is_essential=True)
                return True
            except Exception:
                if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
                self.logger(config.tr("token_expired"), is_essential=True)
                if not self.is_authorizing:
                    self.authorize_user()
        else:
            if not self.is_authorizing:
                self.authorize_user()
        return False

    def authorize_user(self):
        if self.is_authorizing:
            return
            
        self.is_authorizing = True

        def on_code(code):
            webbrowser.open(code.verification_url)
            self.logger(config.tr("auth_req") + f": {code.user_code}", is_essential=True)
            if self.on_code_cb:
                self.root.after(0, lambda: self.on_code_cb(code.user_code))

        def auth_thread():
            try:
                token = self.client.device_auth(on_code=on_code)
                with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                    f.write(token.to_json())
                self.client = Client(token.access_token).init()
                self.is_authorized = True
                self.logger(config.tr("auth_success"), is_essential=True)
                if self.on_success_cb:
                    self.root.after(0, self.on_success_cb)
            except Exception as e:
                self.logger(f"Auth error: {e}", is_essential=True)
            finally:
                self.is_authorizing = False
                
        threading.Thread(target=auth_thread, daemon=True).start()

    def search_track(self, artist, title):
        if not self.is_authorized:
            self.check_token_at_startup()
            if not self.is_authorized: return None
        try:
            query = f"{artist} {title}".strip()
            
            # Если исполнитель пустой (браузер не смог его отдать), ищем только по названию
            if len(artist) < 2: 
                query = title
                
            self.logger(f"Ищем в Яндексе: {query}", is_essential=False)
            search_result = self.client.search(query)
            
            if search_result.tracks and search_result.tracks.results:
                for track in search_result.tracks.results[:3]:
                    track_artist = track.artists[0].name if track.artists else ""
                    track_title = track.title
                    
                    sim_artist = difflib.SequenceMatcher(None, artist.lower(), track_artist.lower()).ratio()
                    sim_title = difflib.SequenceMatcher(None, title.lower(), track_title.lower()).ratio()
                    
                    # Если мы искали только по названию, проверяем только название
                    if len(artist) < 2:
                        if sim_title > 0.6:
                            self.logger(f"✅ Совпадение по названию: {track_title}", is_essential=False)
                            return track
                    else:
                        if sim_artist > 0.5 and sim_title > 0.5:
                            self.logger(f"✅ Совпадение: {track_artist} — {track_title}", is_essential=False)
                            return track
                
                self.logger(f"❌ Низкая схожесть. Возможно, это видео или подкаст.", is_essential=False)
            else:
                self.logger(config.tr("not_found"), is_essential=False)
        except Exception as e:
            self.logger(f"Ошибка поиска: {e}", is_essential=False)
        return None

    def get_lyrics(self, track_id):
        try:
            self.logger(config.tr("fetch_lyrics"), is_essential=False)
            lyrics_info = self.client.tracks_lyrics(track_id)
            if lyrics_info:
                return lyrics_info.fetch_lyrics()
        except Exception:
            pass
        return ""