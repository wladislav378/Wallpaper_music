from pycaw.pycaw import AudioUtilities

def test_audio():
    print("🔍 Сканирование аудио-сессий Windows...")
    try:
        sessions = AudioUtilities.GetAllSessions()
        found = False
        for session in sessions:
            if session.Process:
                found = True
                name = session.Process.name()
                pid = session.ProcessId
                vol = int(session.SimpleAudioVolume.GetMasterVolume() * 100)
                print(f"✅ Найден процесс: {name} (PID: {pid}) | Громкость: {vol}%")
            else:
                print("⚙️ Системный звук (Windows)")
                
        if not found:
            print("⚠️ Вообще нет активных процессов со звуком.")
            print("Включите музыку в Яндекс.Музыке и запустите скрипт снова.")
            
    except Exception as e:
        print(f"❌ Ошибка при получении сессий: {e}")

if __name__ == "__main__":
    test_audio()