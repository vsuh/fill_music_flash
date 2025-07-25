#!/usr/bin/env python3

import os
import random
import shutil
import sys
import threading
import time
import argparse
from queue import Queue
from dotenv import load_dotenv

load_dotenv()
# Конфигурация
FLASH_DRIVE = os.getenv("FLASH_DRIVE", "/mnt/CD")
MUSIC_LIBRARY = os.getenv("MUSIC_LIBRARY", "/mnt/hdd/FILES/Music")
HISTORY_FILE = os.getenv("HISTORY_FILE", os.path.expanduser("~/.flash_music_history"))
ALLOWED_CAPACITY_DEVIATION = float(os.getenv("ALLOWED_CAPACITY_DEVIATION", 0.02))
EXPECTED_SIZE_GB = int(os.getenv("EXPECTED_SIZE_GB", 36))
RESERVE_SIZE = int(os.getenv("RESERVE_SIZE", 100 * 1024**2))
EXTENSIONS = ('.mp3',".mp4")
THREAD_COUNT = int(os.getenv("THREAD_COUNT", 3))

# Глобальные переменные
current_total = 0
copied_count = 0
new_copied = []
total_lock = threading.Lock()
print_lock = threading.Lock()
start_time = time.time()
TARGET_SIZE = 0  

def verify_flash_capacity():
    """Проверяет, что емкость флешки соответствует ожидаемой"""
    try:
        usage = shutil.disk_usage(FLASH_DRIVE)
        total_bytes = usage.total
        expected_min = EXPECTED_SIZE_GB * 1024**3 * (1 - ALLOWED_CAPACITY_DEVIATION)
        expected_max = EXPECTED_SIZE_GB * 1024**3 * (1 + ALLOWED_CAPACITY_DEVIATION)
        
        if not (expected_min <= total_bytes <= expected_max):
            actual_gb = total_bytes / 1024**3
            deviation = abs(actual_gb - EXPECTED_SIZE_GB) / EXPECTED_SIZE_GB * 100
            error_msg = (
                f"ОШИБКА: Неправильный размер флешки!\n"
                f"Ожидалось: {EXPECTED_SIZE_GB}GB ±{ALLOWED_CAPACITY_DEVIATION*100:.1f}%\n"
                f"Фактически: {actual_gb:.2f}GB\n"
                f"Отклонение: {deviation:.2f}%"
            )
            sys.exit(error_msg)
        
        # Устанавливаем целевой размер с учетом резерва
        global TARGET_SIZE
        TARGET_SIZE = total_bytes - RESERVE_SIZE
        return total_bytes
    except Exception as e:
        sys.exit(f"ОШИБКА проверки емкости флешки: {str(e)}")

def clear_flash_drive():
    """Очищает флешку полностью"""
    for item in os.listdir(FLASH_DRIVE):
        item_path = os.path.join(FLASH_DRIVE, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        except Exception as e:
            with print_lock:
                print(f"\nОшибка при удалении {item_path}: {str(e)}")

def get_unique_filename(filename):
    """Генерирует уникальное имя файла в целевой директории"""
    base, ext = os.path.splitext(filename)
    counter = 1
    new_name = filename
    
    while os.path.exists(os.path.join(FLASH_DRIVE, new_name)):
        new_name = f"{base}_{counter}{ext}"
        counter += 1
    
    return new_name

def worker(file_queue):
    """Функция для потока обработки файлов"""
    global current_total, copied_count, new_copied

    while True:
        try:
            file_path = file_queue.get_nowait()
        except Exception:
            break

        try:
            file_size = os.path.getsize(file_path)

            with total_lock:
                # Проверяем, достигли ли целевого размера
                if current_total >= TARGET_SIZE:
                    file_queue.task_done()
                    continue

                # Проверяем свободное место с учетом резерва
                if hasattr(os, "statvfs"):
                    stat = os.statvfs(FLASH_DRIVE)
                    free_space = stat.f_frsize * stat.f_bavail - RESERVE_SIZE
                else:
                    # Для Windows используем shutil.disk_usage
                    free_space = shutil.disk_usage(FLASH_DRIVE).free - RESERVE_SIZE

                if file_size > free_space:
                    file_queue.task_done()
                    continue

            # Генерируем уникальное имя
            dest_filename = get_unique_filename(os.path.basename(file_path))
            dest_path = os.path.join(FLASH_DRIVE, dest_filename)

            # Копируем файл
            shutil.copy2(file_path, dest_path)

            # Получаем реальный размер скопированного файла
            copied_size = os.path.getsize(dest_path)

            with total_lock:
                # Учитываем только успешно скопированные файлы
                if current_total + copied_size <= TARGET_SIZE:
                    current_total += copied_size
                    copied_count += 1
                    new_copied.append(file_path)

        except Exception as e:
            with print_lock:
                print(f"\nОшибка при копировании {file_path}: {str(e)}")
        finally:
            file_queue.task_done()

def update_progress():
    """Обновляет прогресс-бар в одной строке"""
    with total_lock:
        copied = copied_count
        size = current_total
        percent = min(100, size / TARGET_SIZE * 100) if TARGET_SIZE > 0 else 0
    
    progress_bar_length = 50
    filled = int(progress_bar_length * percent / 100)
    bar = '█' * filled + '-' * (progress_bar_length - filled)
    
    sys.stdout.write(f"\rПрогресс: |{bar}| {percent:.1f}% ({copied} файлов, {size/1024**3:.2f}GB/{TARGET_SIZE/1024**3:.2f}GB)")
    sys.stdout.flush()

def calculate_real_usage():
    """Рассчитывает реальное занятое место на флешке"""
    total_size = 0
    for dirpath, _, filenames in os.walk(FLASH_DRIVE):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size

def main():
    global current_total, copied_count, new_copied, start_time, TARGET_SIZE
    start_time = time.time()
    
    # Парсинг аргументов
    parser = argparse.ArgumentParser(description='Заполнение флешки случайными аудиофайлами')
    parser.add_argument('--skip-size-check', action='store_true', help='Пропустить проверку размера флешки')
    args = parser.parse_args()
    
    # Проверка доступности путей
    if not os.path.exists(FLASH_DRIVE):
        sys.exit(f"Ошибка: {FLASH_DRIVE} не существует!")
    
    if not os.path.exists(MUSIC_LIBRARY):
        sys.exit(f"Ошибка: Медиатека {MUSIC_LIBRARY} не найдена!")
    
    # Определение размера флешки
    flash_size = shutil.disk_usage(FLASH_DRIVE).total
    if not args.skip_size_check:
        flash_size = verify_flash_capacity()
    else:
        TARGET_SIZE = flash_size - RESERVE_SIZE
    
    # Очистка флешки
    print("Очищаю флешку...", end='', flush=True)
    clear_flash_drive()
    print("\rФлешка очищена.          ")
    print(f"Обнаружен размер флешки: {flash_size/1024**3:.2f}GB")
    print(f"Целевой размер для заполнения: {TARGET_SIZE/1024**3:.2f}GB (с резервом {RESERVE_SIZE/1024**2}MB)")
    
    # Загрузка истории копирования
    copied_files = set()
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                copied_files = set(line.strip() for line in f)
        except Exception:
            print("Предупреждение: Не удалось прочитать файл истории. Начинаю с чистого листа.")
            copied_files = set()

    # Поиск всех аудиофайлов
    print("Сканирую медиатеку...", end='', flush=True)
    all_files = []
    for root, _, files in os.walk(MUSIC_LIBRARY):
        for file in files:
            if file.lower().endswith(EXTENSIONS):
                full_path = os.path.join(root, file)
                all_files.append(full_path)
    
    # Исключаем файлы из истории
    candidate_files = [f for f in all_files if f not in copied_files]
    
    # Если кандидатов недостаточно - сбрасываем историю
    if not candidate_files:
        print("\rВсе файлы уже были использованы. Сбрасываю историю.", end='', flush=True)
        candidate_files = all_files
        copied_files = set()
    
    # Перемешиваем файлы
    random.shuffle(candidate_files)
    
    # Создаем очередь задач
    file_queue = Queue()
    for file_path in candidate_files:
        file_queue.put(file_path)
    
    # Запускаем потоки
    threads = []
    for i in range(THREAD_COUNT):
        t = threading.Thread(target=worker, args=(file_queue,))
        t.daemon = True
        t.start()
        threads.append(t)
    
    # Отображение прогресса
    print("\nНачинаю копирование:")
    while any(t.is_alive() for t in threads):
        update_progress()
        time.sleep(0.1)
    
    # Финальное обновление прогресса
    update_progress()
    print()
    
    # Обновляем историю
    if new_copied:
        with open(HISTORY_FILE, 'a') as f:
            for path in new_copied:
                f.write(f"{path}\n")
        
        # Рассчитываем реальное использование
        real_used = calculate_real_usage()
        free_space = shutil.disk_usage(FLASH_DRIVE).free
        elapsed_time = time.time() - start_time
        mins, secs = divmod(elapsed_time, 60)
        total_flash = shutil.disk_usage(FLASH_DRIVE).total
        
        print(f"\n{'='*50}")
        print(f"Итоги копирования:")
        print(f" - Физический размер флешки: {total_flash/1024**3:.2f}GB")
        print(f" - Скопировано файлов: {copied_count}")
        print(f" - Суммарный размер файлов: {current_total/1024**3:.2f}GB")
        print(f" - Реально занято места: {real_used/1024**3:.2f}GB")
        print(f" - Свободно: {free_space/1024**3:.2f}GB")
        print(f" - Заполнение: {real_used/total_flash*100:.1f}%")
        print(f" - Добавлено в историю: {len(new_copied)} записей")
        print(f" - Уникальных файлов в истории: {len(copied_files) + len(new_copied)}")
        print(f" - Время выполнения: {int(mins)} мин {int(secs)} сек")
        
        # Проверка расхождения
        discrepancy = abs(real_used - current_total)
        if discrepancy > 1024**3:  # Расхождение более 1GB
            print(f"\n  ВНИМАНИЕ: Обнаружено расхождение между суммарным размером файлов")
            print(f"  и реально занятым местом: {discrepancy/1024**3:.2f}GB")
            print(f"  Это может быть вызвано особенностями файловой системы.")
        
        print(f"{'='*50}")
    else:
        print("Не удалось скопировать ни одного файла.")

if __name__ == "__main__":
    main()
