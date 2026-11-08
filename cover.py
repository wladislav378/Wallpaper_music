import asyncio
import io
import time
import ctypes
import os
import sys
import shutil
import urllib.request
import http.client
import webbrowser
import traceback
import json
import threading
import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
)
from winsdk.windows.storage.streams import DataReader
from yandex_music import Client
from yandex_music.exceptions import UnauthorizedError

# --- ИМПОРТ ДЛЯ ГРОМКОСТИ ---
try:
    from pycaw.pycaw import AudioUtilities
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

http.client._encode = lambda x: x.encode('utf-8')

APP_NAME = "YandexMusicWallpaper"
APP_DATA_DIR = os.path.join(os.environ['APPDATA'], APP_NAME)

if not os.path.exists(APP_DATA_DIR):
    os.makedirs(APP_DATA_DIR)

TOKEN_FILE = os.path.join(APP_DATA_DIR, 'token.json')
WALLPAPER_PATH = os.path.join(APP_DATA_DIR, 'music_wallpaper.jpg')
BACKUP_WALLPAPER_PATH = os.path.join(APP_DATA_DIR, 'original_wallpaper.jpg')

BG_MAIN = "#121212"
BG_SECONDARY = "#282828"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#B3B3B3"
ACCENT = "#1DB954" 
BAR_BG = "#555555" 

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_current_wallpaper():
    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.user32.SystemParametersInfoW(0x0073, 1024, buffer, 0)
    return buffer.value

def set_windows_wallpaper(image_path):
    ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)


class MusicWallpaperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Music Wallpaper")
        self.root.geometry("620x500")
        self.root.configure(bg=BG_MAIN)
        self.root.resizable(False, False)
        
        try:
            icon_image = Image.open(resource_path("icon.ico"))
            self.icon_photo = ImageTk.PhotoImage(icon_image)
            self.root.iconphoto(True, self.icon_photo)
        except Exception:
            pass
            
        current_wp = get_current_wallpaper()
        if current_wp and os.path.exists(current_wp):
            try:
                shutil.copy2(current_wp, BACKUP_WALLPAPER_PATH)
            except Exception:
                pass
                
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.client = Client()
        self.is_running = False
        self.worker_thread = None
        
        self.last_artist = None
        self.last_title = None
        self.current_lyrics = None
        
        self.current_pos = 0.0
        self.current_dur = 0.0
        self.is_dragging = False

        # --- ГРОМКОСТЬ (ТОЛЬКО ПРИЛОЖЕНИЕ) ---
        self.volume_interface = None
        self.current_volume = 100
        self.prev_volume = 100
        self.is_dragging_vol = False

        self.setup_ui()
        self.check_token_at_startup()
        
        if HAS_PYCAW:
            threading.Thread(target=self.volume_sync_loop, daemon=True).start()

    def setup_ui(self):
        self.top_frame = tk.Frame(self.root, bg=BG_MAIN, pady=15, padx=20)
        self.top_frame.pack(fill=tk.X)

        left_top = tk.Frame(self.top_frame, bg=BG_MAIN)
        left_top.pack(side=tk.LEFT, fill=tk.Y)

        self.cover_container = tk.Frame(left_top, width=120, height=120, bg=BG_SECONDARY)
        self.cover_container.pack_propagate(False)
        self.cover_container.pack(side=tk.LEFT)

        self.cover_label = tk.Label(self.cover_container, bg=BG_SECONDARY)
        self.cover_label.pack(fill=tk.BOTH, expand=True)
        
        text_frame = tk.Frame(left_top, bg=BG_MAIN)
        text_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        
        self.title_label = tk.Label(text_frame, text="Трек не играет", font=("Segoe UI", 16, "bold"), fg=TEXT_PRIMARY, bg=BG_MAIN, anchor="w", wraplength=250, justify="left")
        self.title_label.pack(anchor="w", pady=(30, 5))
        
        self.artist_label = tk.Label(text_frame, text="Запустите плеер", font=("Segoe UI", 11), fg=TEXT_SECONDARY, bg=BG_MAIN, anchor="w", wraplength=250, justify="left")
        self.artist_label.pack(anchor="w")

        # Правая часть: Громкость
        if HAS_PYCAW:
            self.vol_container = tk.Frame(self.top_frame, bg=BG_MAIN)
            self.vol_container.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
            
            self.vol_text = tk.Label(self.vol_container, text="---%", font=("Segoe UI", 10, "bold"), fg=TEXT_PRIMARY, bg=BG_MAIN)
            self.vol_text.pack(side=tk.TOP)

            self.vol_canvas = tk.Canvas(self.vol_container, width=40, height=80, bg=BG_MAIN, highlightthickness=0, cursor="hand2")
            self.vol_canvas.pack(side=tk.TOP, pady=5)
            
            self.vol_canvas.bind("<Configure>", self.draw_vol_slider)
            self.vol_canvas.bind("<Button-1>", self.on_vol_click)
            self.vol_canvas.bind("<B1-Motion>", self.on_vol_drag)
            self.vol_canvas.bind("<ButtonRelease-1>", self.on_vol_release)

            self.mute_btn = tk.Button(self.vol_container, text="🔊", font=("Segoe UI", 14), fg=TEXT_SECONDARY, bg=BG_MAIN, bd=0, activebackground=BG_MAIN, activeforeground=TEXT_PRIMARY, command=self.toggle_mute)
            self.mute_btn.pack(side=tk.TOP)

        # Кнопки по центру
        self.controls_frame = tk.Frame(self.root, bg=BG_MAIN, pady=5)
        self.controls_frame.pack(fill=tk.X)

        btn_inner = tk.Frame(self.controls_frame, bg=BG_MAIN)
        btn_inner.pack() 
        
        btn_font = ("Segoe UI", 24)
        
        self.prev_btn = tk.Button(btn_inner, text="⏮", font=btn_font, fg=TEXT_PRIMARY, bg=BG_MAIN, bd=0, activebackground=BG_MAIN, activeforeground=ACCENT, command=lambda: self.media_control("prev"))
        self.prev_btn.pack(side=tk.LEFT, padx=15)

        self.play_btn = tk.Button(btn_inner, text="⏯", font=("Segoe UI", 32), fg=TEXT_PRIMARY, bg=BG_MAIN, bd=0, activebackground=BG_MAIN, activeforeground=ACCENT, command=lambda: self.media_control("play_pause"))
        self.play_btn.pack(side=tk.LEFT, padx=15)

        self.next_btn = tk.Button(btn_inner, text="⏭", font=btn_font, fg=TEXT_PRIMARY, bg=BG_MAIN, bd=0, activebackground=BG_MAIN, activeforeground=ACCENT, command=lambda: self.media_control("next"))
        self.next_btn.pack(side=tk.LEFT, padx=15)

        # Прогресс-бар
        self.progress_frame = tk.Frame(self.root, bg=BG_MAIN, padx=20, pady=15)
        self.progress_frame.pack(fill=tk.X)
        
        self.time_left = tk.Label(self.progress_frame, text="0:00", font=("Segoe UI", 9), fg=TEXT_SECONDARY, bg=BG_MAIN)
        self.time_left.pack(side=tk.LEFT)
        
        self.time_right = tk.Label(self.progress_frame, text="0:00", font=("Segoe UI", 9), fg=TEXT_SECONDARY, bg=BG_MAIN)
        self.time_right.pack(side=tk.RIGHT)
        
        self.canvas_bar = tk.Canvas(self.progress_frame, height=20, bg=BG_MAIN, highlightthickness=0, cursor="hand2")
        self.canvas_bar.pack(fill=tk.X, expand=True, padx=10)
        self.canvas_bar.bind("<Configure>", self.draw_progress_bar)
        self.canvas_bar.bind("<Button-1>", self.on_bar_click)
        self.canvas_bar.bind("<B1-Motion>", self.on_bar_drag)
        self.canvas_bar.bind("<ButtonRelease-1>", self.on_bar_release)

        # Низ
        self.bottom_frame = tk.Frame(self.root, bg=BG_MAIN, pady=15, padx=20)
        self.bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.show_lyrics_var = tk.BooleanVar(value=False)
        self.lyrics_check = tk.Checkbutton(
            self.bottom_frame, text="Текст на обоях", variable=self.show_lyrics_var, 
            command=self.on_lyrics_toggle, font=("Segoe UI", 10), fg=TEXT_PRIMARY,
            bg=BG_MAIN, selectcolor=BG_SECONDARY, activebackground=BG_MAIN, activeforeground=TEXT_PRIMARY, bd=0
        )
        self.lyrics_check.pack(side=tk.LEFT)

        self.toggle_btn = tk.Button(self.bottom_frame, text="▶ Включить", command=self.toggle_worker, bg=ACCENT, fg="white", font=("Segoe UI", 10, "bold"), bd=0, padx=15, pady=5)
        self.toggle_btn.pack(side=tk.RIGHT)

        self.log_btn = tk.Button(self.bottom_frame, text="Лог", command=self.show_log_window, bg=BG_SECONDARY, fg=TEXT_PRIMARY, font=("Segoe UI", 9), bd=0, padx=10, pady=5)
        self.log_btn.pack(side=tk.RIGHT, padx=10)


    # --- ЛОГИКА ГРОМКОСТИ (ПОИСК ПРИЛОЖЕНИЯ) ---
    def find_music_session(self):
        """Ищет аудиопоток Яндекс.Музыки по характерным именам процессов."""
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    name = session.Process.name().lower()
                    # Выводим в лог все процессы с аудио, чтобы вы могли проверить
                    # print(f"[AUDIO] Найден процесс: {name}") 
                    
                    # Ищем Яндекс.Музыку (ru.yandex.desktop, Яндекс Музыка.exe, Y.Music.exe, yandexmusic.exe)
                    if "yandex" in name or "музыка" in name or "music" in name:
                        return session.SimpleAudioVolume
        except Exception:
            pass
        return None

    def volume_sync_loop(self):
        """Следит за громкостью приложения."""
        while True:
            try:
                # Если интерфейс потерян (приложение закрылось), ищем заново
                if not self.volume_interface:
                    self.volume_interface = self.find_music_session()

                if self.volume_interface and not self.is_dragging_vol:
                    sys_vol = int(self.volume_interface.GetMasterVolume() * 100)
                    if sys_vol != self.current_volume:
                        self.current_volume = sys_vol
                        self.root.after(0, self.apply_volume_ui)
                elif not self.volume_interface:
                    # Если приложение не найдено, показываем прочерки
                    if self.current_volume != -1:
                        self.current_volume = -1
                        self.root.after(0, self.apply_volume_ui)
            except Exception:
                self.volume_interface = None
            time.sleep(1)

    def toggle_mute(self):
        if not self.volume_interface:
            self.volume_interface = self.find_music_session()
            if not self.volume_interface: return

        if self.current_volume > 0:
            self.prev_volume = self.current_volume
            self.current_volume = 0
        else:
            self.current_volume = self.prev_volume if self.prev_volume > 0 else 50
        
        self.volume_interface.SetMasterVolume(self.current_volume / 100.0, None)
        self.apply_volume_ui()

    def apply_volume_ui(self):
        if not hasattr(self, 'vol_text'): return
        
        if self.current_volume == -1 or not self.volume_interface:
            self.vol_text.config(text="---%")
            self.mute_btn.config(text="🔇", state=tk.DISABLED)
            self.current_volume = 100 # Сбрасываем для отрисовки
            self.draw_vol_slider()
            return
            
        self.mute_btn.config(state=tk.NORMAL)
        self.vol_text.config(text=f"{self.current_volume}%")
        
        if self.current_volume == 0:
            self.mute_btn.config(text="🔇")
        elif self.current_volume < 50:
            self.mute_btn.config(text="🔉")
        else:
            self.mute_btn.config(text="🔊")
            
        self.draw_vol_slider()

    def draw_vol_slider(self, event=None):
        self.vol_canvas.delete("all")
        w = self.vol_canvas.winfo_width()
        h = self.vol_canvas.winfo_height()
        cx = w // 2
        
        top_y = 10
        bottom_y = h - 10
        
        if h < 20: return

        track_width = 8

        # Фоновая полоса
        self.vol_canvas.create_line(cx, top_y, cx, bottom_y, fill=BAR_BG, width=track_width, capstyle=tk.ROUND)

        # Если приложение не найдено, не рисуем ползунок
        if self.current_volume == -1 or not self.volume_interface:
            return

        ratio = self.current_volume / 100.0
        thumb_y = bottom_y - ratio * (bottom_y - top_y)

        if self.current_volume > 0:
            self.vol_canvas.create_line(cx, bottom_y, cx, thumb_y, fill=TEXT_PRIMARY, width=track_width, capstyle=tk.ROUND)

        r = 6
        self.vol_canvas.create_oval(cx - r, thumb_y - r, cx + r, thumb_y + r, fill=TEXT_PRIMARY, outline="")

    def on_vol_click(self, event):
        if not self.volume_interface: return
        self.is_dragging_vol = True
        self.update_vol_from_mouse(event.y)

    def on_vol_drag(self, event):
        if not self.volume_interface: return
        self.update_vol_from_mouse(event.y)

    def on_vol_release(self, event):
        self.is_dragging_vol = False

    def update_vol_from_mouse(self, y):
        if not self.volume_interface: return
        h = self.vol_canvas.winfo_height()
        top_y = 10
        bottom_y = h - 10
        
        if bottom_y <= top_y: return

        ratio = (bottom_y - y) / (bottom_y - top_y)
        ratio = max(0.0, min(1.0, ratio))
        
        new_vol = int(ratio * 100)
        if new_vol != self.current_volume:
            self.current_volume = new_vol
            try:
                self.volume_interface.SetMasterVolume(self.current_volume / 100.0, None)
            except Exception:
                self.volume_interface = None # Потеряли связь
            self.apply_volume_ui()


    # --- ЛОГИКА ПРОГРЕСС-БАРА ---
    def on_bar_click(self, event):
        if self.current_dur <= 0: return
        self.is_dragging = True
        self.update_pos_from_mouse(event.x)

    def on_bar_drag(self, event):
        if self.current_dur <= 0: return
        self.update_pos_from_mouse(event.x)

    def on_bar_release(self, event):
        if self.current_dur <= 0: return
        self.is_dragging = False
        self.media_control("seek", self.current_pos)

    def update_pos_from_mouse(self, x):
        w = self.canvas_bar.winfo_width()
        if w < 1: return
        ratio = max(0.0, min(1.0, x / w))
        self.current_pos = ratio * self.current_dur
        self.update_progress_ui(self.current_pos, self.current_dur)

    def format_time(self, seconds):
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"

    def draw_progress_bar(self, event=None):
        self.canvas_bar.delete("all")
        w = self.canvas_bar.winfo_width()
        h = 20
        cy = h // 2
        
        if w < 10: return
        
        if self.current_dur <= 0:
            self.canvas_bar.create_line(0, cy, w, cy, fill=BAR_BG, width=4, capstyle=tk.ROUND)
            return

        progress = min(self.current_pos / self.current_dur, 1.0)
        fill_x = w * progress
        
        self.canvas_bar.create_line(0, cy, w, cy, fill=BAR_BG, width=4, capstyle=tk.ROUND)
        if fill_x > 0:
            self.canvas_bar.create_line(0, cy, fill_x, cy, fill=TEXT_PRIMARY, width=4, capstyle=tk.ROUND)
            
        r = 6
        self.canvas_bar.create_oval(fill_x - r, cy - r, fill_x + r, cy + r, fill=TEXT_PRIMARY, outline="")

    def log(self, message):
        self.root.after(0, lambda: self._append_log(message))

    def _append_log(self, message):
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            total_lines = int(self.log_text.index('end-1c').split('.')[0])
            if total_lines > 100:
                self.log_text.delete('1.0', '2.0')
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        else:
            print(message)

    def show_log_window(self):
        if hasattr(self, 'log_window') and self.log_window.winfo_exists():
            self.log_window.lift()
            return
            
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("Лог событий")
        self.log_window.geometry("500x300")
        self.log_window.configure(bg=BG_MAIN)
        
        self.log_text = scrolledtext.ScrolledText(self.log_window, bg=BG_SECONDARY, fg=TEXT_PRIMARY, font=("Consolas", 9), bd=0)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text.config(state=tk.DISABLED)

    def media_control(self, action, value=None):
        def _control():
            try:
                async def _async():
                    sessions = await MediaManager.request_async()
                    session = sessions.get_current_session()
                    if session:
                        if action == "play_pause": await session.try_toggle_play_pause_async()
                        elif action == "next": await session.try_skip_next_async()
                        elif action == "prev": await session.try_skip_previous_async()
                        elif action == "seek" and value is not None:
                            ticks = int(value * 10_000_000)
                            await session.try_change_playback_position_async(ticks)
                asyncio.run(_async())
            except Exception as e:
                self.log(f"Ошибка управления: {e}")
        threading.Thread(target=_control, daemon=True).start()

    def check_token_at_startup(self):
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
                    access_token = token_data.get('access_token')
                self.client = Client(access_token).init()
                self.client.account_status()
            except Exception:
                if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
                self.authorize_user()
        else:
            self.authorize_user()

    def authorize_user(self):
        def on_code(code):
            webbrowser.open(code.verification_url)
            self.root.after(0, lambda: messagebox.showinfo("Авторизация", f"Введите код в браузере:\n\n{code.user_code}"))

        def auth_thread():
            try:
                token = self.client.device_auth(on_code=on_code)
                with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                    f.write(token.to_json())
                self.client = Client(token.access_token).init()
                self.root.after(0, lambda: self.log("✅ Авторизация успешна!"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Ошибка авторизации: {e}"))
        threading.Thread(target=auth_thread, daemon=True).start()

    def toggle_worker(self):
        if not self.is_running:
            self.is_running = True
            self.toggle_btn.config(text="⏹ Стоп", bg="#f44336")
            self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
            self.worker_thread.start()
            self.log("Запуск слежения...")
        else:
            self.stop_worker()

    def stop_worker(self):
        self.is_running = False
        self.toggle_btn.config(text="▶ Включить", bg=ACCENT)
        
        if os.path.exists(BACKUP_WALLPAPER_PATH):
            set_windows_wallpaper(BACKUP_WALLPAPER_PATH)
            
        self.last_artist = None
        self.last_title = None
        self.current_lyrics = None
        self.current_pos = 0
        self.current_dur = 0
        self.update_ui_text(None, None)
        self.cover_label.config(image='')
        self.cover_label.image = None
        self.time_left.config(text="0:00")
        self.time_right.config(text="0:00")
        self.draw_progress_bar()
        self.log("Работа остановлена, обои восстановлены.")

    def on_close(self):
        if self.is_running:
            self.stop_worker()
        self.root.destroy()

    def on_lyrics_toggle(self):
        if self.is_running and self.last_artist and self.last_title:
            threading.Thread(target=self.generate_wallpaper, args=(self.last_artist, self.last_title, True), daemon=True).start()

    def worker_loop(self):
        last_track = None
        
        while self.is_running:
            try:
                artist, title, thumb_data, pos, dur, status = asyncio.run(self.get_media_info())
                
                if artist and title:
                    current_track = f"{artist} - {title}"
                    
                    if current_track != last_track:
                        self.root.after(0, lambda a=artist, t=title: self.update_ui_text(a, t))
                        if thumb_data:
                            self.root.after(0, lambda d=thumb_data: self.update_ui_cover(d))
                        
                        last_track = current_track
                        self.last_artist = artist
                        self.last_title = title
                        self.current_lyrics = None
                        
                        threading.Thread(target=self.generate_wallpaper, args=(artist, title), daemon=True).start()

                    if not self.is_dragging:
                        self.current_dur = dur
                        self.current_pos = pos
                        self.root.after(0, lambda p=self.current_pos, d=self.current_dur: self.update_progress_ui(p, d))

                else:
                    if last_track is not None:
                        self.root.after(0, lambda: self.update_ui_text(None, None))
                        self.current_pos = 0
                        self.current_dur = 0
                        self.root.after(0, lambda: self.update_progress_ui(0, 0))
                        last_track = None
                        
            except Exception:
                pass
            
            time.sleep(0.5)

    def update_progress_ui(self, pos, dur):
        self.time_left.config(text=self.format_time(pos))
        self.time_right.config(text=self.format_time(dur))
        self.draw_progress_bar()

    def update_ui_text(self, artist, title):
        if artist and title:
            self.title_label.config(text=title)
            self.artist_label.config(text=artist)
        else:
            self.title_label.config(text="Трек не играет")
            self.artist_label.config(text="Запустите плеер")

    def update_ui_cover(self, image_bytes):
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = img.resize((120, 120), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.cover_label.config(image=photo)
            self.cover_label.image = photo
        except Exception:
            pass

    async def get_media_info(self):
        try:
            sessions = await MediaManager.request_async()
            session = sessions.get_current_session()
            if not session: return None, None, None, 0, 0, -1
            
            info = await session.try_get_media_properties_async()
            if not info: return None, None, None, 0, 0, -1
            
            pos = 0.0
            dur = 0.0
            status = -1
            
            try:
                playback_info = session.get_playback_info()
                if playback_info:
                    status = playback_info.playback_status
                    
                timeline = session.get_timeline_properties()
                if timeline:
                    dur = timeline.end_time.total_seconds()
                    if dur <= 0:
                        dur = timeline.max_seek_time.total_seconds()
                        
                    raw_pos = timeline.position.total_seconds()
                    last_updated = timeline.last_updated_time
                    
                    if last_updated and status == 4: 
                        now = datetime.datetime.now(datetime.timezone.utc)
                        diff = (now - last_updated).total_seconds()
                        pos = raw_pos + diff
                    else:
                        pos = raw_pos
                        
                    if pos > dur and dur > 0:
                        pos = dur
            except Exception:
                pass
            
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
                except Exception:
                    pass
                
            return info.artist, info.title, thumb_data, pos, dur, status
        except Exception:
            return None, None, None, 0, 0, -1

    def generate_wallpaper(self, artist, title, force_update=False):
        try:
            query = f"{artist} {title}"
            search_result = self.client.search(query)
            if not search_result.tracks or not search_result.tracks.results:
                return
                
            track = search_result.tracks.results[0]
            
            duration_str = ""
            if hasattr(track, 'duration_ms') and track.duration_ms:
                m, s = divmod(int(track.duration_ms / 1000), 60)
                duration_str = f"{m:02d}:{s:02d}"
                
            album_name = ""
            if hasattr(track, 'albums') and track.albums:
                album_name = track.albums[0].title
            
            need_lyrics = self.show_lyrics_var.get()
            if need_lyrics and (self.current_lyrics is None or force_update):
                try:
                    lyrics_info = self.client.tracks_lyrics(track.id)
                    if lyrics_info:
                        self.current_lyrics = lyrics_info.fetch_lyrics()
                    else:
                        self.current_lyrics = ""
                except Exception:
                    self.current_lyrics = ""
                
            cover_url = track.cover_uri.replace("%%", "600x600")
            if cover_url.startswith("//"):
                cover_url = "https:" + cover_url
            elif not cover_url.startswith("http"):
                cover_url = "https://" + cover_url
                
            req = urllib.request.Request(cover_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                cover_data = response.read()
                
            cover_img = Image.open(io.BytesIO(cover_data)).convert("RGB")
            
            user32 = ctypes.windll.user32
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
            
            canvas = Image.new("RGB", (screen_width, screen_height), (0, 0, 0))
            
            x_offset = (screen_width - cover_img.width) // 2
            y_offset = (screen_height - cover_img.height) // 2 - 50
            canvas.paste(cover_img, (x_offset, y_offset))
            
            draw = ImageDraw.Draw(canvas)

            def get_font(size, bold=False):
                font_names = ["msyhbd.ttc" if bold else "msyh.ttc", "arialuni.ttf", "segoeuib.ttf" if bold else "segoeui.ttf", "arialbd.ttf" if bold else "arial.ttf"]
                for name in font_names:
                    path = f"C:\\Windows\\Fonts\\{name}"
                    if os.path.exists(path):
                        try: return ImageFont.truetype(path, size)
                        except: continue
                return ImageFont.load_default()

            font_artist = get_font(28, bold=False)
            font_album = get_font(20, bold=False)
            font_time = get_font(20, bold=False)

            if album_name and album_name.strip().lower() != title.strip().lower():
                album_text = f"— {album_name.upper()} —" 
                draw.text((screen_width // 2, y_offset - 40), album_text, font=font_album, fill="#777777", anchor="ma")

            text_y = y_offset + cover_img.height + 25 
            
            title_size = 40
            while draw.textlength(title, font=get_font(title_size, bold=True)) > (cover_img.width + 200) and title_size > 16:
                title_size -= 2
            font_title = get_font(title_size, bold=True)

            draw.text((screen_width // 2, text_y), title, font=font_title, fill="white", anchor="ma")
            draw.text((screen_width // 2, text_y + 50), artist, font=font_artist, fill="#aaaaaa", anchor="ma")
            
            if duration_str:
                draw.text((screen_width // 2, text_y + 100), duration_str, font=font_time, fill="#666666", anchor="ma")
            
            if need_lyrics and self.current_lyrics:
                canvas = self.draw_lyrics_columns(canvas, self.current_lyrics, text_y, get_font)
            
            canvas.save(WALLPAPER_PATH, "JPEG", quality=95)
            set_windows_wallpaper(WALLPAPER_PATH)
            self.log(f"✅ Обои обновлены: {title}")
            
        except Exception as e:
            self.log(f"Ошибка обоев: {e}")

    def draw_lyrics_columns(self, canvas, lyrics_text, text_y, font_getter):
        canvas_rgba = canvas.convert("RGBA")
        overlay = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        screen_w, screen_h = canvas.size
        cover_w = 600
        cover_x = (screen_w - cover_w) // 2
        
        margin_edge = 30      
        gap_to_cover = 30     
        
        left_max_w = cover_x - margin_edge - gap_to_cover
        right_max_w = screen_w - (cover_x + cover_w) - margin_edge - gap_to_cover
        
        box_width = min(left_max_w, right_max_w)
        left_x = margin_edge
        right_x = screen_w - margin_edge - box_width
        
        box_top = 30
        box_bottom = screen_h - 30 
        box_height = box_bottom - box_top
        
        pad_x = 25
        safe_max_width = box_width - (pad_x * 2)

        raw_lines = [line.strip() for line in lyrics_text.split('\n') if line.strip()]
        best_font = None
        best_line_height = 0
        left_lines = []
        right_lines = []
        wrapped_lines = []
        
        text_max_height = box_height - 120 
        
        for size in range(40, 9, -1):
            font = font_getter(size, bold=False)
            line_height = int(size * 1.25) 
            
            wrapped_lines = []
            for line in raw_lines:
                words = line.split()
                current_line = []
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    if draw.textlength(test_line, font=font) <= safe_max_width:
                        current_line.append(word)
                    else:
                        if current_line:
                            wrapped_lines.append(' '.join(current_line))
                        current_line = [word]
                if current_line:
                    wrapped_lines.append(' '.join(current_line))

            half_len = len(wrapped_lines) // 2
            temp_left = wrapped_lines[:half_len]
            temp_right = wrapped_lines[half_len:]
            current_text_height = max(len(temp_left), len(temp_right)) * line_height

            if current_text_height <= text_max_height:
                best_font = font
                best_line_height = line_height
                left_lines = temp_left
                right_lines = temp_right
                break 

        if not best_font:
            size = 10
            best_font = font_getter(size, bold=False)
            best_line_height = int(size * 1.25)
            max_lines = text_max_height // best_line_height
            left_lines = wrapped_lines[:max_lines]
            right_lines = wrapped_lines[max_lines:max_lines*2]

        text_block_height = max(len(left_lines), len(right_lines)) * best_line_height
        text_start_y = box_top + (box_height - text_block_height) // 2
        
        text_color = (255, 255, 255, 220) 
        box_bg_color = (20, 20, 20, 180)  
        box_outline_color = (255, 255, 255, 40) 

        if left_lines:
            box_left = [left_x, box_top, left_x + box_width, box_bottom]
            draw.rounded_rectangle(box_left, radius=15, fill=box_bg_color, outline=box_outline_color, width=2)
            current_y = text_start_y
            for line in left_lines:
                draw.text((left_x + pad_x, current_y), line, font=best_font, fill=text_color, anchor="la")
                current_y += best_line_height

        if right_lines:
            box_right = [right_x, box_top, right_x + box_width, box_bottom]
            draw.rounded_rectangle(box_right, radius=15, fill=box_bg_color, outline=box_outline_color, width=2)
            current_y = text_start_y
            for line in right_lines:
                draw.text((right_x + pad_x, current_y), line, font=best_font, fill=text_color, anchor="la")
                current_y += best_line_height

        return Image.alpha_composite(canvas_rgba, overlay).convert("RGB")

if __name__ == "__main__":
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Wladislav.YandexMusicWallpaper.1")
    
    root = tk.Tk()
    app = MusicWallpaperApp(root)
    root.mainloop()