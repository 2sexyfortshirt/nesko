import threading
import os
import boto3
import urllib.parse
from dotenv import load_dotenv
from models import Audio, Video, CountryCategory
from config import db


# Заглушка для старых вызовов isAlive()
if not hasattr(threading.Thread, "isAlive"):
    threading.Thread.isAlive = threading.Thread.is_alive

load_dotenv()

# ==== Переменные окружения ====
SPACES_KEY = os.getenv("SPACES_KEY")
SPACES_SECRET = os.getenv("SPACES_SECRET")
SPACES_REGION = os.getenv("SPACES_REGION", "fra1")
SPACES_BUCKET = os.getenv("SPACES_BUCKET")
SPACES_ENDPOINT = os.getenv("SPACES_ENDPOINT")   # должен быть https://fra1.digitaloceanspaces.com

# Проверка переменных
if not all([SPACES_KEY, SPACES_SECRET, SPACES_BUCKET, SPACES_ENDPOINT]):
    raise ValueError("❌ Не все переменные окружения заданы в .env!")

# ==== DigitalOcean Spaces S3 клиент ====
session = boto3.session.Session()
client = session.client(
    "s3",
    region_name=SPACES_REGION,
    endpoint_url=SPACES_ENDPOINT,   # Используем правильный endpoint!
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
)

# ==== Расширения ====
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".aac", ".flac")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".avi", ".mkv")


# ==== Генерация публичной ссылки ====
def build_public_url(key):
    return f"https://{SPACES_BUCKET}.{SPACES_REGION}.digitaloceanspaces.com/{key}"


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




# ==== Presigned URL ====
def get_presigned_view_url(filename, expires_in=3600):
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": SPACES_BUCKET, "Key": filename},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        print(f"Ошибка presigned URL: {e}")
        return None


# ==== Основной метод — загрузка аудио/видео из Spaces в БД ====
def list_media(sync_spaces=True):
    audios = []
    videos = []

    # Получаем текущие записи из БД
    db_audios = {a.filename: a for a in Audio.query.all()}
    db_videos = {v.filename: v for v in Video.query.all()}
    categories_map = {c.id: c.name for c in CountryCategory.query.all()}

    if sync_spaces:
        # Получаем список объектов из DO Spaces
        resp = client.list_objects_v2(Bucket=SPACES_BUCKET)
        keys = [obj['Key'] for obj in resp.get('Contents', [])]

        for key in keys:
            ext = os.path.splitext(key)[1].lower()
            if ext in AUDIO_EXTENSIONS and key not in db_audios:
                # Добавляем новое аудио в БД
                new_audio = Audio(
                    filename=key,
                    url=build_public_url(key),
                    artist="Unknown",
                    genre="Unknown",
                    price=0,
                    category_id=None
                )
                db.session.add(new_audio)
                db_audios[key] = new_audio

            elif ext in VIDEO_EXTENSIONS and key not in db_videos:
                # Добавляем новое видео в БД
                new_video = Video(
                    filename=key,
                    url=build_public_url(key),
                    title=os.path.splitext(os.path.basename(key))[0],
                    category_id=None
                )
                db.session.add(new_video)
                db_videos[key] = new_video

        db.session.commit()

    # Подготавливаем списки для вывода
    for a in db_audios.values():
        audios.append({
            "filename": a.filename,
            "url": a.url,
            "artist": a.artist,
            "genre": a.genre,
            "price": a.price,
            "thumb_url": a.thumb_url,
            "category_id": a.category_id,
            "category_name": categories_map.get(a.category_id, "Без категории"),
            'original_name': a.original_name,
        })

    for v in db_videos.values():
        videos.append({
            "filename": v.filename,
            "url": v.url,
            "title": v.title,
            "category_id": v.category_id,
            "category_name": categories_map.get(v.category_id, "Без категории"),
            'original_name': v.original_name,
        })

    print(f"Найдено аудио: {len(audios)}, видео: {len(videos)}")
    return audios, videos
    if __name__ == "__main__":
        from main import app  # импортируем Flask-приложение для контекста


    with app.app_context():
    # Просто вызываем функцию, которая уже определена в этом файле
        audios, videos = list_media()

        print("🎬 Аудио:")
        for a in audios:
            print(f"{a['filename']} | {a['artist']} | {a['genre']} | {a['category_name']}")

        print("\n🎵 Видео:")
        for v in videos:
            print(f"{v['filename']} | {v['title']} | {v['category_name']}")

