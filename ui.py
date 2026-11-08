import os
import io
import time
import ctypes
import urllib.request
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk
from PIL import Image, ImageTk, ImageDraw
import config
from config import (
    BACKUP_WALLPAPER_PATH, WALLPAPER_PATH, set_windows_wallpaper, get_current_wallpaper, resource_path
)
from yandex_api import YandexAPI
from media_control import MediaController
from renderer import generate_wallpaper

class MusicWallpaperApp:
    def __init__(self, root):
        self.root = root
        self.root.title(config.tr("app_title"))
        self.root.geometry("650x650")
        self.root.resizable(False, False)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        try:
            icon_image = Image.open(resource_path("icon.ico"))
            self.icon_photo = ImageTk.PhotoImage(icon_image)
            self.root.iconphoto(True, self.icon_photo)
        except Exception:
            pass

        self.settings = config.load_settings()
        config.CURRENT_THEME = self.settings.get("theme", "Темная")
        config.CURRENT_LANG = self.settings.get("language", "RU")
            
        self.is_running = True 
        self.is_closing = False
        self.worker_thread = None
        self.current_pos = 0.0
        self.current_dur = 0.0
        self.is_dragging = False
        self.is_dragging_vol = False
        self.last_track = None
        self.current_lyrics = None
        self.current_volume = 100
        self.prev_volume = 100
        self.last_thumb_data = None
        self.is_playing_state = False
        self.auth_code = None

        self.show_lyrics_var = tk.BooleanVar(value=self.settings.get("show_lyrics", False))
        self.is_log_open = False
        self.log_cache = []
        self.settings_win = None

        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("Лог событий")
        self.log_window.geometry("500x300")
        self.log_window.withdraw()
        self.log_window.protocol("WM_DELETE_WINDOW", self.hide_log_window)
        
        self.log_text = scrolledtext.ScrolledText(self.log_window, font=("Consolas", 9), bd=0)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text.config(state=tk.DISABLED)

        self.yandex = YandexAPI(self.root, self.log, self.show_auth_code, self.on_auth_success)
        self.media = MediaController(self.log)
        
        self.yandex.check_token_at_startup()
        
        self.draw_ui()
        self.apply_volume_ui()
        self.volume_sync_loop()
        
        self.root.after(200, self.update_window_frame)
        
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()

    def show_auth_code(self, code):
        self.auth_code = code
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.log(config.tr("auth_copied"), is_essential=False)
        self.update_auth_ui()

    def on_auth_success(self):
        self.update_auth_ui()
        self.last_track = None

    def update_auth_ui(self):
        if not self.yandex.is_authorized:
            self.cover_label.pack_forget()
            self.auth_label.pack(fill=tk.BOTH, expand=True)
            
            if self.auth_code:
                text = f"{config.tr('auth_instruction')}\n\n{self.auth_code}\n\n{config.tr('auth_copied')}\n{config.tr('auth_waiting')}"
                self.auth_label.config(text=text, fg=config.get_colors()["ACCENT"])
            else:
                self.auth_label.config(text=f"{config.tr('auth_req')}...", fg=config.get_colors()["TEXT_SECONDARY"])
            
            self.title_label.config(text=config.tr("auth_req"))
            self.artist_label.config(text="Yandex Music")
        else:
            self.auth_label.pack_forget()
            self.cover_label.pack(fill=tk.BOTH, expand=True)
            if self.last_thumb_data:
                self.update_ui_cover(self.last_thumb_data)
            if self.last_track:
                artist, title = self.last_track.split(" - ", 1)
                self.title_label.config(text=title)
                self.artist_label.config(text=artist)

    def update_window_frame(self):
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd:
                is_dark = 1 if config.CURRENT_THEME not in ["Светлая", "Ванильная"] else 0
                dark_mode = ctypes.c_int(is_dark)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        except Exception:
            pass

    def log(self, message, is_essential=False):
        if is_essential and not self.is_log_open:
            self.log_cache.append(message) 
        if self.is_log_open:
            self.root.after(0, lambda: self._append_log(message))
        else:
            print(message)

    def _append_log(self, message):
        if hasattr(self, 'log_text'):
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            total_lines = int(self.log_text.index('end-1c').split('.')[0])
            if total_lines > 200: 
                self.log_text.delete('1.0', '2.0')
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

    def show_log_window(self):
        self.is_log_open = True
        self.log_window.deiconify()
        self.log_window.lift()
        if self.log_cache:
            self.log_text.config(state=tk.NORMAL)
            for msg in self.log_cache:
                self.log_text.insert(tk.END, f"[Cached] {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log_cache.clear()

    def hide_log_window(self):
        self.is_log_open = False
        self.log_window.withdraw()

    def get_button_image(self, shape, color, size=40):
        S = 4
        img = Image.new("RGBA", (size*S, size*S), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        w, h = size*S, size*S
        
        if shape == "prev":
            draw.polygon([(w*0.6, h*0.2), (w*0.6, h*0.8), (w*0.2, h*0.5)], fill=color)
            draw.polygon([(w*0.9, h*0.2), (w*0.9, h*0.8), (w*0.5, h*0.5)], fill=color)
        elif shape == "next":
            draw.polygon([(w*0.4, h*0.2), (w*0.4, h*0.8), (w*0.8, h*0.5)], fill=color)
            draw.polygon([(w*0.1, h*0.2), (w*0.1, h*0.8), (w*0.5, h*0.5)], fill=color)
        elif shape == "play":
            draw.polygon([(w*0.35, h*0.2), (w*0.35, h*0.8), (w*0.75, h*0.5)], fill=color)
        elif shape == "pause":
            cw = w * 0.15
            ch = h * 0.5
            y0 = (h - ch) / 2
            y1 = y0 + ch
            draw.rectangle([w*0.3, y0, w*0.45, y1], fill=color)
            draw.rectangle([w*0.55, y0, w*0.7, y1], fill=color)
            
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)

    def draw_ui(self):
        colors = config.get_colors()
        self.root.configure(bg=colors["BG_MAIN"])
        self.root.title(config.tr("app_title"))
        
        for widget in self.root.winfo_children():
            if widget not in (self.log_window, self.settings_win):
                widget.destroy()

        center_frame = tk.Frame(self.root, bg=colors["BG_MAIN"])
        center_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.cover_container = tk.Frame(center_frame, width=250, height=250, bg=colors["BG_SECONDARY"])
        self.cover_container.pack_propagate(False)
        self.cover_container.pack(side=tk.TOP, pady=(20, 15))

        self.cover_label = tk.Label(self.cover_container, bg=colors["BG_SECONDARY"])
        self.auth_label = tk.Label(self.cover_container, text="", font=("Segoe UI", 13, "bold"), bg=colors["BG_SECONDARY"], justify="center", wraplength=230)

        if self.last_thumb_data and self.yandex.is_authorized:
            self.update_ui_cover(self.last_thumb_data)

        self.title_label = tk.Label(center_frame, text=config.tr("not_playing"), font=("Segoe UI", 24, "bold"), fg=colors["TEXT_PRIMARY"], bg=colors["BG_MAIN"], justify="center", wraplength=550)
        self.title_label.pack(side=tk.TOP, pady=(5, 5))

        self.artist_label = tk.Label(center_frame, text=config.tr("start_player"), font=("Segoe UI", 14), fg=colors["TEXT_SECONDARY"], bg=colors["BG_MAIN"], justify="center")
        self.artist_label.pack(side=tk.TOP, pady=(0, 25))

        controls_frame = tk.Frame(center_frame, bg=colors["BG_MAIN"])
        controls_frame.pack(side=tk.TOP, pady=(0, 15))
        
        self.img_prev = self.get_button_image("prev", colors["TEXT_PRIMARY"])
        self.img_prev_hover = self.get_button_image("prev", colors["ACCENT"])
        self.img_next = self.get_button_image("next", colors["TEXT_PRIMARY"])
        self.img_next_hover = self.get_button_image("next", colors["ACCENT"])
        self.img_play = self.get_button_image("play", colors["TEXT_PRIMARY"], size=60)
        self.img_play_hover = self.get_button_image("play", colors["ACCENT"], size=60)
        self.img_pause = self.get_button_image("pause", colors["TEXT_PRIMARY"], size=60)
        self.img_pause_hover = self.get_button_image("pause", colors["ACCENT"], size=60)

        self.prev_btn = tk.Label(controls_frame, image=self.img_prev, bg=colors["BG_MAIN"], cursor="hand2")
        self.prev_btn.pack(side=tk.LEFT, padx=15)
        self.prev_btn.bind("<Button-1>", lambda e: self.media.control("prev"))
        self.prev_btn.bind("<Enter>", lambda e: self.prev_btn.config(image=self.img_prev_hover))
        self.prev_btn.bind("<Leave>", lambda e: self.prev_btn.config(image=self.img_prev))

        self.play_btn = tk.Label(controls_frame, image=self.img_play, bg=colors["BG_MAIN"], cursor="hand2")
        self.play_btn.pack(side=tk.LEFT, padx=15)
        self.play_btn.bind("<Button-1>", lambda e: self.media.control("play_pause"))
        self.play_btn.bind("<Enter>", lambda e: self.on_play_hover(True))
        self.play_btn.bind("<Leave>", lambda e: self.on_play_hover(False))

        self.next_btn = tk.Label(controls_frame, image=self.img_next, bg=colors["BG_MAIN"], cursor="hand2")
        self.next_btn.pack(side=tk.LEFT, padx=15)
        self.next_btn.bind("<Button-1>", lambda e: self.media.control("next"))
        self.next_btn.bind("<Enter>", lambda e: self.next_btn.config(image=self.img_next_hover))
        self.next_btn.bind("<Leave>", lambda e: self.next_btn.config(image=self.img_next))

        self.progress_frame = tk.Frame(center_frame, bg=colors["BG_MAIN"], padx=50) 
        self.progress_frame.pack(side=tk.TOP, fill=tk.X) 
        
        self.time_left = tk.Label(self.progress_frame, text="0:00", font=("Segoe UI", 9), fg=colors["TEXT_SECONDARY"], bg=colors["BG_MAIN"])
        self.time_left.pack(side=tk.LEFT)
        
        self.time_right = tk.Label(self.progress_frame, text="0:00", font=("Segoe UI", 9), fg=colors["TEXT_SECONDARY"], bg=colors["BG_MAIN"])
        self.time_right.pack(side=tk.RIGHT)
        
        self.canvas_bar = tk.Canvas(self.progress_frame, height=20, bg=colors["BG_MAIN"], highlightthickness=0, cursor="hand2")
        self.canvas_bar.pack(fill=tk.X, expand=True, padx=10)
        self.canvas_bar.bind("<Configure>", self.draw_progress_bar)
        self.canvas_bar.bind("<Button-1>", self.on_bar_click)
        self.canvas_bar.bind("<B1-Motion>", self.on_bar_drag)
        self.canvas_bar.bind("<ButtonRelease-1>", self.on_bar_release)

        self.settings_btn = tk.Button(self.root, text=config.tr("settings"), font=("Segoe UI", 10), fg=colors["TEXT_SECONDARY"], bg=colors["BG_MAIN"], bd=0, activebackground=colors["BG_MAIN"], activeforeground=colors["TEXT_PRIMARY"], command=self.show_settings)
        self.settings_btn.place(x=20, rely=0.95, anchor="sw")

        # --- НОВОЕ МЕНЮ ВЫБОРА ИСТОЧНИКА (Справа снизу) ---
        self.source_menu = tk.Menu(self.root, tearoff=0, bg=colors["BG_SECONDARY"], fg=colors["TEXT_PRIMARY"], activebackground=colors["ACCENT"], activeforeground="#000000")
        
        self.source_btn = tk.Button(self.root, text=f"🎵 {config.tr('auto')} ▾", font=("Segoe UI", 10, "bold"), fg=colors["TEXT_PRIMARY"], bg=colors["BG_SECONDARY"], bd=0, padx=10, pady=5, activebackground=colors["BG_MAIN"], activeforeground=colors["ACCENT"], command=self.show_source_menu)
        self.source_btn.place(relx=0.95, rely=0.95, anchor="se")
        
        self.update_source_button_text()

        self.vol_container = tk.Frame(self.root, bg=colors["BG_MAIN"])
        self.vol_container.place(relx=0.95, y=30, anchor="ne")
        
        self.vol_text = tk.Label(self.vol_container, text="---%", font=("Segoe UI", 10, "bold"), fg=colors["TEXT_PRIMARY"], bg=colors["BG_MAIN"])
        self.vol_text.pack(side=tk.TOP)

        self.vol_canvas = tk.Canvas(self.vol_container, width=40, height=120, bg=colors["BG_MAIN"], highlightthickness=0, cursor="hand2")
        self.vol_canvas.pack(side=tk.TOP, pady=10)
        self.vol_canvas.bind("<Configure>", self.draw_vol_slider)
        self.vol_canvas.bind("<Button-1>", self.on_vol_click)
        self.vol_canvas.bind("<B1-Motion>", self.on_vol_drag)
        self.vol_canvas.bind("<ButtonRelease-1>", self.on_vol_release)

        self.mute_btn = tk.Button(self.vol_container, text="🔊", font=("Segoe UI", 16), fg=colors["TEXT_SECONDARY"], bg=colors["BG_MAIN"], bd=0, activebackground=colors["BG_MAIN"], activeforeground=colors["TEXT_PRIMARY"], command=self.toggle_mute)
        self.mute_btn.pack(side=tk.TOP)

        self.log_window.configure(bg=colors["BG_MAIN"])
        self.log_text.configure(bg=colors["BG_SECONDARY"], fg=colors["TEXT_PRIMARY"])

        self.apply_volume_ui()
        self.update_progress_ui(self.current_pos, self.current_dur)
        self.update_play_btn_image()
        self.update_auth_ui()
        self.root.after(100, self.update_window_frame)

    def show_source_menu(self):
        self.source_menu.delete(0, tk.END)
        
        # Добавляем фиксированные пункты
        self.source_menu.add_command(label=config.tr("none"), command=lambda: self.set_source("None"))
        self.source_menu.add_command(label=config.tr("auto"), command=lambda: self.set_source("Auto"))
        self.source_menu.add_separator()
        
        # Получаем динамический список
        sources = self.media.get_available_sources()
        for app_id, name in sources:
            self.source_menu.add_command(label=name, command=lambda a=app_id: self.set_source(a))
            
        # Открываем меню рядом с кнопкой
        x = self.source_btn.winfo_rootx()
        y = self.source_btn.winfo_rooty() - self.source_menu.winfo_reqheight()
        self.source_menu.post(x, y)

    def set_source(self, source_id):
        self.settings["media_source"] = source_id
        config.save_settings(self.settings)
        self.update_source_button_text()
        self.last_track = None # Сбрасываем, чтобы трек перечитался

    def update_source_button_text(self):
        current = self.settings.get("media_source", "Auto")
        if current == "Auto":
            display = config.tr("auto")
        elif current == "None":
            display = config.tr("none")
        else:
            # Ищем красивое имя
            sources = self.media.get_available_sources()
            display = next((name for app_id, name in sources if app_id == current), current)
            
        self.source_btn.config(text=f"🎵 {display} ▾")

    def on_play_hover(self, is_hover):
        if self.is_playing_state:
            img = self.img_pause_hover if is_hover else self.img_pause
        else:
            img = self.img_play_hover if is_hover else self.img_play
        self.play_btn.config(image=img)

    def update_play_btn_image(self):
        if self.is_playing_state:
            img = self.img_pause
        else:
            img = self.img_play
        self.play_btn.config(image=img)

    def update_play_btn(self, is_playing):
        if self.is_playing_state != is_playing:
            self.is_playing_state = is_playing
            self.root.after(0, self.update_play_btn_image)

    def show_settings(self):
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return

        colors = config.get_colors()
        self.settings_win = tk.Toplevel(self.root)
        self.settings_win.title(config.tr("settings"))
        self.settings_win.geometry("350x350")
        self.settings_win.configure(bg=colors["BG_MAIN"])
        self.settings_win.resizable(False, False)
        self.settings_win.protocol("WM_DELETE_WINDOW", self.close_settings)

        tk.Label(self.settings_win, text=config.tr("theme"), font=("Segoe UI", 10, "bold"), fg=colors["TEXT_PRIMARY"], bg=colors["BG_MAIN"]).pack(pady=(15, 5), anchor="w", padx=20)
        theme_combo = ttk.Combobox(self.settings_win, values=list(config.THEMES.keys()), state="readonly", font=("Segoe UI", 10))
        theme_combo.set(config.CURRENT_THEME)
        theme_combo.pack(fill=tk.X, padx=20, pady=5)
        
        def on_theme_change(event):
            config.CURRENT_THEME = theme_combo.get()
            self.settings["theme"] = config.CURRENT_THEME
            config.save_settings(self.settings)
            self.close_settings()
            self.draw_ui()
            self.force_wallpaper_update()

        theme_combo.bind("<<ComboboxSelected>>", on_theme_change)

        tk.Label(self.settings_win, text=config.tr("language"), font=("Segoe UI", 10, "bold"), fg=colors["TEXT_PRIMARY"], bg=colors["BG_MAIN"]).pack(pady=(10, 5), anchor="w", padx=20)
        lang_combo = ttk.Combobox(self.settings_win, values=["RU", "EN"], state="readonly", font=("Segoe UI", 10))
        lang_combo.set(config.CURRENT_LANG)
        lang_combo.pack(fill=tk.X, padx=20, pady=5)
        
        def on_lang_change(event):
            config.CURRENT_LANG = lang_combo.get()
            self.settings["language"] = config.CURRENT_LANG
            config.save_settings(self.settings)
            self.close_settings()
            self.draw_ui()

        lang_combo.bind("<<ComboboxSelected>>", on_lang_change)

        lyrics_cb = tk.Checkbutton(
            self.settings_win, text=config.tr("show_lyrics"), 
            variable=self.show_lyrics_var, command=self.on_lyrics_toggle,
            font=("Segoe UI", 10), fg=colors["TEXT_PRIMARY"], bg=colors["BG_MAIN"], 
            selectcolor=colors["BG_SECONDARY"], activebackground=colors["BG_MAIN"], 
            activeforeground=colors["TEXT_PRIMARY"], bd=0
        )
        lyrics_cb.pack(anchor="w", padx=20, pady=(10, 5))

        tk.Label(self.settings_win, text=config.tr("blur_level"), font=("Segoe UI", 10, "bold"), fg=colors["TEXT_PRIMARY"], bg=colors["BG_MAIN"]).pack(anchor="w", padx=20, pady=(10, 0))
        
        blur_mapping = {
            config.tr("blur_0"): 0,
            config.tr("blur_30"): 30,
            config.tr("blur_80"): 80,
            config.tr("blur_150"): 150,
            config.tr("blur_250"): 250
        }
        
        current_blur = self.settings.get("blur_radius", 80)
        current_name = config.tr("blur_80")
        for name, val in blur_mapping.items():
            if val == current_blur:
                current_name = name
                break
                
        blur_combo = ttk.Combobox(self.settings_win, values=list(blur_mapping.keys()), state="readonly", font=("Segoe UI", 10))
        blur_combo.set(current_name)
        blur_combo.pack(fill=tk.X, padx=20, pady=5)

        def on_blur_change(event):
            selected_name = blur_combo.get()
            self.settings["blur_radius"] = blur_mapping[selected_name]
            config.save_settings(self.settings)
            self.force_wallpaper_update()

        blur_combo.bind("<<ComboboxSelected>>", on_blur_change)

        tk.Button(
            self.settings_win, text=config.tr("open_log"), command=self.show_log_window,
            bg=colors["BG_SECONDARY"], fg=colors["TEXT_PRIMARY"], font=("Segoe UI", 10), bd=0, padx=10, pady=8
        ).pack(fill=tk.X, padx=20, pady=(20, 0))
        
    def close_settings(self):
        if self.settings_win:
            self.settings_win.destroy()
            self.settings_win = None

    def volume_sync_loop(self):
        if not self.is_dragging_vol:
            sys_vol = self.media.get_volume()
            if sys_vol != -1 and sys_vol != self.current_volume:
                self.current_volume = sys_vol
                self.apply_volume_ui()
            elif sys_vol == -1 and self.current_volume != -1:
                self.current_volume = -1
                self.apply_volume_ui()
        self.root.after(1000, self.volume_sync_loop)

    def toggle_mute(self):
        if self.current_volume == -1:
            self.media.find_music_session(verbose=True)
            return
        if self.current_volume > 0:
            self.prev_volume = self.current_volume
            self.current_volume = 0
        else:
            self.current_volume = self.prev_volume if self.prev_volume > 0 else 50
        self.media.set_volume(self.current_volume)
        self.apply_volume_ui()

    def apply_volume_ui(self):
        colors = config.get_colors()
        if self.current_volume == -1:
            self.vol_text.config(text="---%", fg=colors["TEXT_PRIMARY"])
            self.mute_btn.config(text="🔇", state=tk.DISABLED)
            self.draw_vol_slider()
            return
        self.mute_btn.config(state=tk.NORMAL)
        self.vol_text.config(text=f"{self.current_volume}%", fg=colors["TEXT_PRIMARY"])
        self.mute_btn.config(text="🔇" if self.current_volume == 0 else ("🔉" if self.current_volume < 50 else "🔊"), fg=colors["TEXT_SECONDARY"])
        self.draw_vol_slider()

    def draw_vol_slider(self, event=None):
        colors = config.get_colors()
        self.vol_canvas.delete("all")
        w = self.vol_canvas.winfo_width()
        h = self.vol_canvas.winfo_height()
        if h < 20: return
        cx = w // 2
        top_y, bottom_y = 10, h - 10
        self.vol_canvas.create_line(cx, top_y, cx, bottom_y, fill=colors["BAR_BG"], width=8, capstyle=tk.ROUND)
        if self.current_volume == -1: return
        thumb_y = bottom_y - (self.current_volume / 100.0) * (bottom_y - top_y)
        if self.current_volume > 0:
            self.vol_canvas.create_line(cx, bottom_y, cx, thumb_y, fill=colors["TEXT_PRIMARY"], width=8, capstyle=tk.ROUND)
        self.vol_canvas.create_oval(cx-6, thumb_y-6, cx+6, thumb_y+6, fill=colors["TEXT_PRIMARY"], outline="")

    def on_vol_click(self, event):
        if self.current_volume == -1: 
            self.media.find_music_session(verbose=True)
            return
        self.is_dragging_vol = True
        self.update_vol_from_mouse(event.y)

    def on_vol_drag(self, event):
        if self.current_volume == -1: return
        self.update_vol_from_mouse(event.y)

    def on_vol_release(self, event):
        self.is_dragging_vol = False

    def update_vol_from_mouse(self, y):
        h = self.vol_canvas.winfo_height()
        top_y, bottom_y = 10, h - 10
        ratio = max(0.0, min(1.0, (bottom_y - y) / (bottom_y - top_y)))
        self.current_volume = int(ratio * 100)
        self.media.set_volume(self.current_volume)
        self.apply_volume_ui()

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
        self.media.control("seek", self.current_pos)

    def update_pos_from_mouse(self, x):
        w = self.canvas_bar.winfo_width()
        if w < 1: return
        ratio = max(0.0, min(1.0, x / w))
        self.current_pos = ratio * self.current_dur
        self.update_progress_ui(self.current_pos, self.current_dur)

    def draw_progress_bar(self, event=None):
        colors = config.get_colors()
        self.canvas_bar.delete("all")
        w, h = self.canvas_bar.winfo_width(), 20
        cy = h // 2
        if w < 10: return
        if self.current_dur <= 0:
            self.canvas_bar.create_line(0, cy, w, cy, fill=colors["BAR_BG"], width=4, capstyle=tk.ROUND)
            return
        fill_x = w * min(self.current_pos / self.current_dur, 1.0)
        self.canvas_bar.create_line(0, cy, w, cy, fill=colors["BAR_BG"], width=4, capstyle=tk.ROUND)
        if fill_x > 0:
            self.canvas_bar.create_line(0, cy, fill_x, cy, fill=colors["TEXT_PRIMARY"], width=4, capstyle=tk.ROUND)
        self.canvas_bar.create_oval(fill_x-6, cy-6, fill_x+6, cy+6, fill=colors["TEXT_PRIMARY"], outline="")

    def format_time(self, seconds):
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"

    def update_progress_ui(self, pos, dur):
        self.time_left.config(text=self.format_time(pos))
        self.time_right.config(text=self.format_time(dur))
        self.draw_progress_bar()

    def stop_worker(self):
        self.is_closing = True
        self.is_running = False
        time.sleep(0.5) 
        
        if os.path.exists(BACKUP_WALLPAPER_PATH): 
            self.log(f"Восстанавливаем обои из {BACKUP_WALLPAPER_PATH}", is_essential=True)
            abs_path = os.path.abspath(BACKUP_WALLPAPER_PATH)
            set_windows_wallpaper(abs_path)
            time.sleep(2.0)
        else:
            self.log(f"Файл {BACKUP_WALLPAPER_PATH} не найден! Обои не восстановлены.", is_essential=True)

    def on_close(self):
        try:
            if self.is_running:
                self.stop_worker()
            config.save_settings(self.settings)
        except Exception as e:
            print(f"Error on close: {e}")
        finally:
            time.sleep(0.5)
            self.root.destroy()

    def worker_loop(self):
        self.last_track = None
        while self.is_running:
            if not self.yandex.is_authorized:
                time.sleep(0.5)
                continue

            # Передаем выбранный источник
            source = self.settings.get("media_source", "Auto")
            artist, title, thumb_data, pos, dur, status = self.media.get_media_info(preferred_source=source)
            
            if artist and title:
                current_track = f"{artist} - {title}"
                if current_track != self.last_track:
                    self.root.after(0, lambda a=artist, t=title: self.update_ui_text(a, t))
                    
                    track_data = self.yandex.search_track(artist, title)
                    if track_data:
                        try:
                            cover_url = track_data.cover_uri.replace("%%", "400x400")
                            if cover_url.startswith("//"): cover_url = "https:" + cover_url
                            elif not cover_url.startswith("http"): cover_url = "https://" + cover_url
                            
                            req = urllib.request.Request(cover_url, headers={'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(req) as response:
                                hq_thumb_data = response.read()
                                
                            self.last_thumb_data = hq_thumb_data
                            self.root.after(0, lambda d=hq_thumb_data: self.update_ui_cover(d))
                        except Exception:
                            if thumb_data:
                                self.last_thumb_data = thumb_data
                                self.root.after(0, lambda d=thumb_data: self.update_ui_cover(d))
                        
                        if self.show_lyrics_var.get():
                            self.current_lyrics = self.yandex.get_lyrics(track_data.id)
                        
                        blur = self.settings.get("blur_radius", 80)
                        
                        threading.Thread(target=generate_wallpaper, args=(artist, title, track_data, self.current_lyrics, self.show_lyrics_var.get(), blur, lambda: self.is_closing), daemon=True).start()
                        self.log(f"{config.tr('w_update')} {title}", is_essential=False)
                    elif thumb_data:
                        self.last_thumb_data = thumb_data
                        self.root.after(0, lambda d=thumb_data: self.update_ui_cover(d))

                    self.last_track = current_track
                    self.current_lyrics = None

                is_playing = (status == 4)
                if self.is_playing_state != is_playing:
                    self.is_playing_state = is_playing
                    self.root.after(0, self.update_play_btn_image)

                if not self.is_dragging:
                    self.current_dur, self.current_pos = dur, pos
                    self.root.after(0, lambda p=self.current_pos, d=self.current_dur: self.update_progress_ui(p, d))
            else:
                if self.last_track is not None:
                    self.root.after(0, lambda: self.update_ui_text(None, None))
                    self.current_pos, self.current_dur = 0, 0
                    self.root.after(0, lambda: self.update_progress_ui(0, 0))
                    self.last_track = None
                if self.is_playing_state:
                    self.is_playing_state = False
                    self.root.after(0, self.update_play_btn_image)
                    
            time.sleep(0.5)

    def update_ui_text(self, artist, title):
        if artist and title:
            self.title_label.config(text=title)
            self.artist_label.config(text=artist)
        else:
            self.title_label.config(text=config.tr("not_playing"))
            self.artist_label.config(text=config.tr("start_player"))

    def update_ui_cover(self, image_bytes):
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((250, 250), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.cover_label.config(image=photo)
            self.cover_label.image = photo
        except Exception:
            pass

    def on_lyrics_toggle(self):
        self.settings["show_lyrics"] = self.show_lyrics_var.get()
        config.save_settings(self.settings)
        self.force_wallpaper_update()

    def force_wallpaper_update(self):
        if self.is_running and self.last_track and self.yandex.is_authorized:
            artist, title = self.last_track.split(" - ", 1)
            track_data = self.yandex.search_track(artist, title)
            if track_data:
                if self.show_lyrics_var.get() and not self.current_lyrics:
                    self.current_lyrics = self.yandex.get_lyrics(track_data.id)
                blur = self.settings.get("blur_radius", 80)
                generate_wallpaper(artist, title, track_data, self.current_lyrics, self.show_lyrics_var.get(), blur, lambda: self.is_closing)