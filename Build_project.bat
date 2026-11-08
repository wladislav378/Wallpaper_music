@echo off
chcp 65001 >nul
title Сборка Yandex Music Wallpaper
cd /d "%~dp0"

echo ===================================================
echo Очистка старых файлов сборки...
echo ===================================================
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist YandexMusicWallpaper.spec del YandexMusicWallpaper.spec

echo ===================================================
echo Проверка наличия иконки...
echo ===================================================
if not exist "icon.ico" (
    echo [ВНИМАНИЕ] Файл icon.ico не найден в текущей папке!
    echo Сборка продолжится, но иконка может не примениться.
    echo.
)

echo ===================================================
echo Сборка приложения (это может занять пару минут)...
echo ===================================================
:: Если вы используете конкретное окружение Anaconda, раскомментируйте строку ниже и укажите его имя
:: call conda activate music-wp

:: Запускаем PyInstaller через python -m, чтобы наверняка использовать нужное окружение
python -m PyInstaller --noconsole --name YandexMusicWallpaper --icon=icon.ico --add-data "icon.ico;." --hidden-import winsdk.windows.media.control --hidden-import winsdk.windows.storage.streams main.py

echo.
echo ===================================================
echo Сборка завершена!
echo Ваш файл .exe находится в папке "dist".
echo ===================================================
pause