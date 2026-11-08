import os
import sys
import json
import ctypes
import shutil

APP_NAME = "YandexMusicWallpaper"
APP_DATA_DIR = os.path.join(os.environ['APPDATA'], APP_NAME)

if not os.path.exists(APP_DATA_DIR):
    os.makedirs(APP_DATA_DIR)

TOKEN_FILE = os.path.join(APP_DATA_DIR, 'token.json')
WALLPAPER_PATH = os.path.join(APP_DATA_DIR, 'music_wallpaper.jpg')
BACKUP_WALLPAPER_PATH = os.path.join(APP_DATA_DIR, 'original_wallpaper.jpg')
SETTINGS_FILE = os.path.join(APP_DATA_DIR, 'settings.json')

TRANSLATIONS = {
    "RU": {
        "app_title": "Music Wallpaper",
        "not_playing": "Трек не играет",
        "start_player": "Запустите плеер",
        "settings": "⚙ Настройки",
        "theme": "Тема оформления:",
        "language": "Язык интерфейса:",
        "show_lyrics": "Отображать текст песни на обоях",
        "open_log": "📄 Открыть лог событий",
        "blur_level": "Фон обоев (размытие):",
        "blur_0": "Выключено",
        "blur_30": "Легкое",
        "blur_80": "Среднее",
        "blur_150": "Сильное",
        "blur_250": "Очень сильное",
        "no_audio": "Яндекс.Музыка не найдена. Ищем браузеры...",
        "found_app": "Подключено к приложению:",
        "found_browser": "Подключено к браузеру:",
        "auth_req": "Требуется авторизация",
        "auth_success": "✅ Авторизация успешна!",
        "token_valid": "✅ Токен действителен.",
        "token_expired": "❌ Токен просрочен. Удаляем...",
        "searching": "Ищем трек в Яндексе:",
        "not_found": "❌ Трек не найден в Яндексе.",
        "fetch_lyrics": "Загрузка текста песни...",
        "no_lyrics": "Текст не найден.",
        "w_update": "✅ Обои обновлены:",
        "w_error": "🔥 Ошибка обоев:",
        "voice_error": "❌ Ошибка звука:",
        "close_log": "Закрыть",
        "auth_instruction": "Введите этот код в браузере:",
        "auth_waiting": "Ожидание ввода...",
        "auth_copied": "📋 Код автоматически скопирован",
        "media_source": "Источник звука",
        "auto": "Авто",
        "none": "Отключено"
    },
    "EN": {
        "app_title": "Music Wallpaper",
        "not_playing": "Not playing",
        "start_player": "Start the player",
        "settings": "⚙ Settings",
        "theme": "Theme:",
        "language": "Language:",
        "show_lyrics": "Show lyrics on wallpaper",
        "open_log": "📄 Open event log",
        "blur_level": "Wallpaper background (blur):",
        "blur_0": "Disabled",
        "blur_30": "Light",
        "blur_80": "Medium",
        "blur_150": "Strong",
        "blur_250": "Very Strong",
        "no_audio": "Yandex Music not found. Searching browsers...",
        "found_app": "Connected to app:",
        "found_browser": "Connected to browser:",
        "auth_req": "Authorization required",
        "auth_success": "✅ Authorization successful!",
        "token_valid": "✅ Token is valid.",
        "token_expired": "❌ Token expired. Removing...",
        "searching": "Searching track in Yandex:",
        "not_found": "❌ Track not found in Yandex.",
        "fetch_lyrics": "Fetching lyrics...",
        "no_lyrics": "Lyrics not found.",
        "w_update": "✅ Wallpaper updated:",
        "w_error": "🔥 Wallpaper error:",
        "voice_error": "❌ Audio error:",
        "close_log": "Close",
        "auth_instruction": "Enter this code in your browser:",
        "auth_waiting": "Waiting for input...",
        "auth_copied": "📋 Code automatically copied",
        "media_source": "Media source",
        "auto": "Auto",
        "none": "None"
    }
}

THEMES = {
    "Темная": {"BG_MAIN": "#121212", "BG_SECONDARY": "#282828", "TEXT_PRIMARY": "#FFFFFF", "TEXT_SECONDARY": "#B3B3B3", "ACCENT": "#1DB954", "BAR_BG": "#555555"},
    "Светлая": {"BG_MAIN": "#F0F0F0", "BG_SECONDARY": "#FFFFFF", "TEXT_PRIMARY": "#000000", "TEXT_SECONDARY": "#555555", "ACCENT": "#0078D7", "BAR_BG": "#CCCCCC"},
    "Ванильная": {"BG_MAIN": "#F5F5DC", "BG_SECONDARY": "#FFFFFF", "TEXT_PRIMARY": "#333333", "TEXT_SECONDARY": "#666666", "ACCENT": "#FF9800", "BAR_BG": "#E0E0E0"},
    "Неон": {"BG_MAIN": "#0A001A", "BG_SECONDARY": "#1A0033", "TEXT_PRIMARY": "#00FFFF", "TEXT_SECONDARY": "#FF00FF", "ACCENT": "#00FF00", "BAR_BG": "#330066"}
}

DEFAULT_SETTINGS = {"theme": "Темная", "language": "RU", "show_lyrics": False, "blur_radius": 80, "media_source": "Auto"}

CURRENT_THEME = "Темная"
CURRENT_LANG = "RU"

def tr(key):
    return TRANSLATIONS.get(CURRENT_LANG, TRANSLATIONS["RU"]).get(key, key)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except Exception:
            pass
    save_settings(DEFAULT_SETTINGS)
    return DEFAULT_SETTINGS

def save_settings(settings_dict):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_dict, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка сохранения настроек: {e}")

def get_colors():
    return THEMES[CURRENT_THEME]

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_current_wallpaper():
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        ctypes.windll.user32.SystemParametersInfoW(0x0073, 1024, buffer, 0)
        return buffer.value
    except Exception:
        return ""

def set_windows_wallpaper(image_path):
    try:
        ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)
    except Exception as e:
        print(f"Error setting wallpaper: {e}")

def backup_current_wallpaper():
    if os.path.exists(BACKUP_WALLPAPER_PATH):
        return
        
    current_wp = get_current_wallpaper()
    if current_wp and os.path.exists(current_wp) and "music_wallpaper" not in current_wp.lower():
        try:
            from PIL import Image
            img = Image.open(current_wp).convert("RGB")
            img.save(BACKUP_WALLPAPER_PATH, "JPEG", quality=95)
            print(f"✅ Сохранены исходные обои (через PIL): {current_wp}")
            return
        except Exception as e:
            print(f"❌ Не удалось сохранить текущие обои: {e}")
            try:
                with open(os.path.join(APP_DATA_DIR, "backup_error.txt"), "w", encoding="utf-8") as f:
                    f.write(f"Current WP: {current_wp}\nError: {e}")
            except:
                pass

    default_wp = r"C:\Windows\Web\Wallpaper\Windows\img0.jpg"
    if os.path.exists(default_wp):
        try:
            from PIL import Image
            img = Image.open(default_wp).convert("RGB")
            img.save(BACKUP_WALLPAPER_PATH, "JPEG", quality=95)
            print("✅ Сохранены стандартные обои Windows.")
        except Exception as e:
            print(f"❌ Не удалось сохранить стандартные обои: {e}")