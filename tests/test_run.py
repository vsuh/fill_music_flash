import os
import tempfile
import shutil
import pytest

from run import (
    get_unique_filename,
    clear_flash_drive,
    verify_flash_capacity,
    calculate_real_usage,
    FLASH_DRIVE,
)

@pytest.fixture
def temp_flash_drive(tmp_path, monkeypatch):
    # Подменяем FLASH_DRIVE на временную папку
    monkeypatch.setattr("run.FLASH_DRIVE", str(tmp_path))
    yield tmp_path

def test_get_unique_filename(temp_flash_drive, monkeypatch):
    # Создаём файл с именем "song.mp3"
    file_path = temp_flash_drive / "song.mp3"
    file_path.write_text("test")
    monkeypatch.setattr("run.FLASH_DRIVE", str(temp_flash_drive))
    # Должен вернуть уникальное имя
    unique = get_unique_filename("song.mp3")
    assert unique != "song.mp3"
    assert unique.startswith("song_")
    assert unique.endswith(".mp3")

def test_clear_flash_drive(temp_flash_drive, monkeypatch):
    # Создаём файлы и папки
    (temp_flash_drive / "file1.mp3").write_text("a")
    (temp_flash_drive / "file2.txt").write_text("b")
    os.mkdir(temp_flash_drive / "dir1")
    (temp_flash_drive / "dir1" / "file3.mp3").write_text("c")
    monkeypatch.setattr("run.FLASH_DRIVE", str(temp_flash_drive))
    clear_flash_drive()
    assert not any(temp_flash_drive.iterdir())

def test_calculate_real_usage(temp_flash_drive, monkeypatch):
    # Создаём файлы
    f1 = temp_flash_drive / "a.mp3"
    f2 = temp_flash_drive / "b.mp3"
    f1.write_bytes(b"1" * 100)
    f2.write_bytes(b"2" * 200)
    monkeypatch.setattr("run.FLASH_DRIVE", str(temp_flash_drive))
    size = calculate_real_usage()
    assert size == 300

def test_verify_flash_capacity(monkeypatch, tmp_path):
    # Подменяем FLASH_DRIVE и параметры
    fake_size = 2 * 1024**3  # 2GB
    class FakeUsage:
        total = fake_size
    monkeypatch.setattr("run.FLASH_DRIVE", str(tmp_path))
    monkeypatch.setattr("run.EXPECTED_SIZE_GB", 2)
    monkeypatch.setattr("run.ALLOWED_CAPACITY_DEVIATION", 0.1)
    monkeypatch.setattr("shutil.disk_usage", lambda path: FakeUsage())
    monkeypatch.setattr("run.RESERVE_SIZE", 0)
    # Не должно выбрасывать исключение
    assert verify_flash_capacity() == fake_size

    # Проверка выхода при неправильном размере
    monkeypatch.setattr("run.EXPECTED_SIZE_GB", 1)
    with pytest.raises(SystemExit):
        verify_flash_capacity()
