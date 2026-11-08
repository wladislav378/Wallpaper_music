import ctypes
import sys
import tkinter as tk
import atexit
import config
from ui import MusicWallpaperApp

def restore_wallpaper_on_exit():
    """Гарантированно возвращает исходные обои при выходе (даже если программа упала)"""
    if config.os.path.exists(config.BACKUP_WALLPAPER_PATH):
        config.set_windows_wallpaper(config.BACKUP_WALLPAPER_PATH)

if __name__ == "__main__":
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YandexMusicWallpaper.App.1")
    
    # 1. САМОЕ ПЕРВОЕ ДЕЙСТВИЕ: Сохраняем обои
    config.backup_current_wallpaper()
    
    # 2. Регистрируем восстановление обоев при выходе
    atexit.register(restore_wallpaper_on_exit)
    
    # 3. Запускаем интерфейс
    root = tk.Tk()
    app = MusicWallpaperApp(root)
    root.mainloop()