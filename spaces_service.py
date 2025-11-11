
import threading
import json
DATA_DIR = "data"

# Заглушка для старых вызовов isAlive()
if not hasattr(threading.Thread, "isAlive"):
    threading.Thread.isAlive = threading.Thread.is_alive
import os
import boto3
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

print("SPACES_KEY:", os.getenv("SPACES_KEY"))
print("SPACES_SECRET:", os.getenv("SPACES_SECRET"))
print("SPACES_BUCKET:", os.getenv("SPACES_BUCKET"))

# ==== Параметры DigitalOcean Spaces из переменных окружения ====
SPACES_KEY = os.getenv("SPACES_KEY")
SPACES_SECRET = os.getenv("SPACES_SECRET")
SPACES_REGION = os.getenv("SPACES_REGION", "fra1")  # например fra1

SPACES_ENDPOINT = os.getenv("SPACES_ENDPOINT")
SPACES_BUCKET = os.getenv("SPACES_BUCKET")

if not all([SPACES_KEY, SPACES_SECRET, SPACES_BUCKET,SPACES_ENDPOINT,SPACES_REGION]):
    print("SPACES_KEY:", SPACES_KEY)
    print("SPACES_SECRET:", SPACES_SECRET)
    print("SPACES_BUCKET:", SPACES_BUCKET)
    print("SPACES_ENDPOINT:", SPACES_ENDPOINT)

    raise ValueError("Не заданы переменные окружения для DigitalOcean Spaces")

# ==== Создаем клиент S3 (S3-совместимый) ====
session = boto3.session.Session()
client = session.client(
    's3',
    region_name=SPACES_REGION,
    endpoint_url=f'https://{SPACES_REGION}.digitaloceanspaces.com',
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET
)


VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".aac", ".ogg", ".flac")
# ==== Загрузка файла ====
def upload_file(file_obj, filename):
    """
    Загружает файл в DigitalOcean Spaces
    :param file_obj: объект файла (file-like)
    :param filename: имя файла, которое будет в Space
    :return: публичный URL файла
    """
    client.upload_fileobj(file_obj, SPACES_BUCKET, filename, ExtraArgs={'ACL': 'public-read'})
    return f"https://{SPACES_BUCKET}.{SPACES_REGION}.digitaloceanspaces.com/{filename}"

# ==== Удаление файла ====
def delete_object(filename):
    """
    Удаляет файл из Spaces
    :param filename: имя файла в Space
    """
    client.delete_object(Bucket=SPACES_BUCKET, Key=filename)

# ==== Получение временной ссылки (presigned) ====
def get_presigned_view_url(filename, expires_in=3600):
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": SPACES_BUCKET, "Key": filename},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        print(f"Ошибка генерации presigned URL: {e}")
        return None

def list_media():
    """Возвращает список аудио и видео файлов из JSON и DO Spaces"""
    videos_path = os.path.join(DATA_DIR, "videos.json")
    covers_path = os.path.join(DATA_DIR, "covers.json")

    # --- Загружаем JSON ---
    try:
        with open(covers_path, "r", encoding="utf-8") as f:
            covers_metadata = json.load(f)
    except FileNotFoundError:
        covers_metadata = []

    try:
        with open(videos_path, "r", encoding="utf-8") as f:
            videos_metadata = json.load(f)
    except FileNotFoundError:
        videos_metadata = []

    audios = []
    videos = []

    # --- Добавляем данные из JSON ---
    audio_filenames = {cover["filename"] for cover in covers_metadata}
    for cover in covers_metadata:
        audios.append({
            "filename": cover["filename"],
            "url": cover["url"],
            "artist": cover.get("artist"),
            "genre": cover.get("genre"),
            "price": cover.get("price", 100)
        })

    video_filenames = {v["filename"] for v in videos_metadata}
    for video in videos_metadata:
        videos.append({
            "filename": video["filename"],
            "url": video["url"],
            "title": video.get("title", os.path.splitext(video["filename"])[0])
        })

    # --- Проверяем файлы из DO Spaces ---
    resp = client.list_objects_v2(Bucket=SPACES_BUCKET)
    for obj in resp.get('Contents', []):
        key = obj['Key']
        filename = os.path.basename(key)

        if key.lower().endswith(('.mp3', '.wav', '.ogg')):
            if filename not in audio_filenames:
                audios.append({
                    "filename": filename,
                    "url": f"/stream/{key}",
                    "artist": "artist",
                    "genre": "genre",
                    "price": 100
                })

        elif key.lower().endswith(('.mp4', '.webm')):
            if filename not in video_filenames:
                new_video = {
                    "filename": filename,
                    "url": f"/stream/{key}",
                    "title": os.path.splitext(filename)[0]
                }
                videos.append(new_video)
                videos_metadata.append(new_video)  # 👈 Добавляем в JSON-данные тоже

    # --- Сохраняем обновлённый videos.json ---
    with open(videos_path, "w", encoding="utf-8") as f:
        json.dump(videos_metadata, f, ensure_ascii=False, indent=2)

    return audios, videos


if __name__ == "__main__":
    audios, videos = list_media()
    print("🎬 covers:")
    for a in audios:
        print(a)
    print("\n🎵 video:")
    for v in videos:
        print(v)