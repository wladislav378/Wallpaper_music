from yandex_music.ynison import simple

# Вставьте сюда ваш access_token от Яндекс.Музыки
TOKEN = "ВАШ_ТОКЕН"

def main():
    print("🔍 Пытаемся получить текущий трек через Ynison...")
    
    try:
        # Получаем текущий трек. Это блокирующий вызов.
        current_track = simple.get_current_track(TOKEN)
        
        if current_track:
            # У объекта current_track есть много полей, нас интересуют основные
            print("\n✅ Успех! Ynison вернул данные:")
            print(f"   🎵 Название: {current_track.title}")
            # У трека может быть несколько исполнителей, выведем первого
            artist_name = current_track.artists[0].name if current_track.artists else "Неизвестен"
            print(f"   👤 Исполнитель: {artist_name}")
            print(f"   🆔 ID трека: {current_track.id}")
            
            # Дополнительно можно посмотреть на активное устройство
            # (потребуется открыть ещё одну сессию, но для теста сойдёт)
            # active_device = simple.get_active_device(TOKEN)
            # print(f"   📱 Устройство: {active_device.info.title}")
            
        else:
            print("\n⚠️ Ynison вернул пустой ответ. Возможно, музыка на паузе или очередь пуста.")
            
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {e}")
        print("   Убедитесь, что токен верный, а на аккаунте сейчас что-то играет.")

if __name__ == "__main__":
    main()