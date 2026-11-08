import asyncio
import datetime
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
)
from winsdk.windows.storage.streams import DataReader
import config

try:
    from pycaw.pycaw import AudioUtilities
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

class MediaController:
    def __init__(self, logger_func):
        self.volume_interface = None
        self.logger = logger_func
        self.last_found_app = None
        self.find_music_session(verbose=True)

    def find_music_session(self, verbose=False):
        if not HAS_PYCAW:
            return None
        try:
            sessions = AudioUtilities.GetAllSessions()
            
            for session in sessions:
                if session.Process:
                    name = session.Process.name().lower()
                    if "яндекс" in name or "yandex" in name or "музыка" in name or "music" in name:
                        if self.last_found_app != name:
                            self.logger(f"{config.tr('found_app')} {session.Process.name()}", is_essential=True)
                            self.last_found_app = name
                        self.volume_interface = session.SimpleAudioVolume
                        return self.volume_interface
                        
            if self.last_found_app != "browser":
                self.logger(config.tr("no_audio"), is_essential=False)
                
            for session in sessions:
                if session.Process:
                    name = session.Process.name().lower()
                    if "browser" in name or "chrome" in name or "edge" in name:
                        if self.last_found_app != name:
                            self.logger(f"{config.tr('found_browser')} {session.Process.name()}", is_essential=True)
                            self.last_found_app = name
                        self.volume_interface = session.SimpleAudioVolume
                        return self.volume_interface
                        
        except Exception as e:
            self.logger(f"{config.tr('voice_error')} {e}", is_essential=True)
        return None

    def get_volume(self):
        if not self.volume_interface:
            self.find_music_session(verbose=False)
        if self.volume_interface:
            try:
                return int(self.volume_interface.GetMasterVolume() * 100)
            except Exception:
                self.volume_interface = None
        return -1

    def set_volume(self, val):
        if not self.volume_interface:
            self.find_music_session(verbose=False)
        if self.volume_interface:
            try:
                self.volume_interface.SetMasterVolume(val / 100.0, None)
            except Exception:
                self.volume_interface = None

    # --- НОВЫЙ МЕТОД: Получение доступных источников ---
    def get_available_sources(self):
        async def _get():
            sources = set()
            try:
                manager = await MediaManager.request_async()
                sessions = manager.get_sessions()
                for s in sessions:
                    if s.source_app_user_model_id:
                        # Очищаем ID для красоты (например, 'chrome.exe' -> 'Chrome')
                        app_id = s.source_app_user_model_id
                        name = app_id.split('.')[-1].capitalize() if '.' in app_id else app_id.capitalize()
                        sources.add((app_id, name))
            except Exception:
                pass
            return list(sources)
        return asyncio.run(_get())

    async def _get_info(self, preferred_source="Auto"):
        try:
            manager = await MediaManager.request_async()
            
            if preferred_source == "None":
                return None, None, None, 0, 0, -1
                
            session = None
            if preferred_source == "Auto":
                session = manager.get_current_session()
            else:
                # Ищем конкретный источник
                for s in manager.get_sessions():
                    if s.source_app_user_model_id == preferred_source:
                        session = s
                        break
                        
            if not session: return None, None, None, 0, 0, -1
            
            info = await session.try_get_media_properties_async()
            if not info: return None, None, None, 0, 0, -1

            source_app = session.source_app_user_model_id.lower() if session.source_app_user_model_id else ""
            
            if preferred_source == "Auto":
                ignored_apps = ["telegram", "discord", "steam", "whatsapp", "skype", "slack"]
                if any(app in source_app for app in ignored_apps):
                    return None, None, None, 0, 0, -1

            raw_artist = info.artist if info.artist else ""
            raw_title = info.title if info.title else ""
            
            self.logger(f"[SMTC] Source: {preferred_source} | Artist: '{raw_artist}' | Title: '{raw_title}'", is_essential=False)

            artist = raw_artist
            title = raw_title

            garbage_artists = ["yandex", "browser", "музыка", "music", "youtube", "soundcloud", "vk", "spotify", "яндекс"]
            if not artist or any(g in artist.lower() for g in garbage_artists):
                if " - " in title:
                    parts = title.split(" - ", 1)
                    artist = parts[0].strip()
                    title = parts[1].strip()
                elif " — " in title:
                    parts = title.split(" — ", 1)
                    artist = parts[0].strip()
                    title = parts[1].strip()
            
            pos = 0.0
            dur = 0.0
            status = -1
            
            try:
                playback_info = session.get_playback_info()
                if playback_info: status = playback_info.playback_status
                timeline = session.get_timeline_properties()
                if timeline:
                    dur = timeline.end_time.total_seconds()
                    if dur <= 0: dur = timeline.max_seek_time.total_seconds()
                    raw_pos = timeline.position.total_seconds()
                    last_updated = timeline.last_updated_time
                    if last_updated and status == 4: 
                        now = datetime.datetime.now(datetime.timezone.utc)
                        pos = raw_pos + (now - last_updated).total_seconds()
                    else:
                        pos = raw_pos
                    if pos > dur and dur > 0: pos = dur
            except Exception: pass
            
            thumb_data = None
            if info.thumbnail:
                try:
                    stream = await info.thumbnail.open_read_async()
                    reader = DataReader(stream)
                    await reader.load_async(stream.size)
                    buffer = bytearray(stream.size)
                    reader.read_bytes(buffer)
                    thumb_data = bytes(buffer)
                    stream.close()
                except Exception: pass
                
            return artist, title, thumb_data, pos, dur, status
        except Exception:
            return None, None, None, 0, 0, -1

    def get_media_info(self, preferred_source="Auto"):
        return asyncio.run(self._get_info(preferred_source))

    async def _control(self, action, value=None):
        try:
            manager = await MediaManager.request_async()
            session = manager.get_current_session() # Управляем текущим, если не выбрано иное
            if session:
                if action == "play_pause": await session.try_toggle_play_pause_async()
                elif action == "next": await session.try_skip_next_async()
                elif action == "prev": await session.try_skip_previous_async()
                elif action == "seek" and value is not None:
                    await session.try_change_playback_position_async(int(value * 10_000_000))
        except Exception as e:
            self.logger(f"Media Control Error: {e}", is_essential=True)

    def control(self, action, value=None):
        asyncio.run(self._control(action, value))