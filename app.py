
import threading

# Заглушка для старых вызовов isAlive()
if not hasattr(threading.Thread, "isAlive"):
    threading.Thread.isAlive = threading.Thread.is_alive



from flask import (
    Flask, render_template, redirect, url_for, send_file,
    request, flash, jsonify, session, abort, Response
)
from flask_cors import CORS
from spaces_service import get_presigned_view_url, upload_file, delete_object, list_media

import os, json, uuid
os.makedirs("data", exist_ok=True)
AUDIOS_JSON = os.path.join("data", "covers.json")
VIDEOS_JSON = os.path.join("data", "videos.json")

if not os.path.exists(AUDIOS_JSON):
    with open(AUDIOS_JSON, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

if not os.path.exists(VIDEOS_JSON):
    with open(VIDEOS_JSON, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)



app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET", "supersecret_local_change_me")

# ----- пути -----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----- админ конфиг из .env -----
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "neSko567___2341")


from spaces_service import client, SPACES_BUCKET,SPACES_REGION

# ----- загрузка/сохранение JSON -----
def load_covers():
    with open(AUDIOS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def save_covers(audios):
    with open(AUDIOS_JSON, "w", encoding="utf-8") as f:
        json.dump(audios, f, ensure_ascii=False, indent=2)

def load_videos():
    with open(VIDEOS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def save_videos(videos):
    with open(VIDEOS_JSON, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)

# ======== публичная часть (index, fake-buy, download) ========
@app.route("/")
def index():
    query = request.args.get("q", "").lower()
    audios, videos = list_media()

    # Подготовим каждый аудио-объект с нужными полями
    audio_covers = []
    for a in audios:
        cover = {
            "filename": a.get("filename"),
            "url": a.get("url", f"/stream/{a.get('filename')}"),
            "artist": a.get("artist"),
            "genre": a.get("genre"),
            "price": a.get("price", 0)
        }
        audio_covers.append(cover)

    # Фильтруем по поисковому запросу
    if query:
        audio_covers = [a for a in audio_covers if query in a['filename'].lower()
                                               or query in a['artist'].lower()
                                               or query in a['genre'].lower()]

    return render_template("index.html", covers=audio_covers, videos=videos, query=query)

# одноразовые токены в памяти
download_tokens = {}
from flask_cors import cross_origin
@app.route("/stream/<path:key>")
@cross_origin()
def stream(key):
    try:
        obj = client.get_object(Bucket=SPACES_BUCKET, Key=key)
        def generate():
            for chunk in obj['Body'].iter_chunks(chunk_size=1024*64):
                yield chunk
        content_type = "audio/mpeg" if key.lower().endswith(".mp3") else "video/mp4"
        return Response(generate(), content_type=content_type)
    except client.exceptions.NoSuchKey:
        return "File not found", 404

@app.route("/fake-buy/<path:filename>", methods=["POST"])
def fake_buy(filename):
    return jsonify({
        "success": True,
        "download_url": f"/stream/{filename}"
    })
# ===== скачивание по токену =====
@app.route("/download/<token>")
def download(token):
    if token not in download_tokens:
        return "⛔ Ссылка недействительна или уже использована.", 410

    filename = download_tokens.pop(token)
    audios = load_covers()
    audio = next((c for c in audios if c["filename"] == filename), None)

    if not audio:
        return "Файл не найден", 404

    # редирект на временную ссылку
    presigned_url = get_presigned_view_url(filename, expires_in=3600)
    return redirect(presigned_url)
# ======== админ: login / logout / admin panel / delete / add ========

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    next_url = request.args.get("next") or url_for("admin")

    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")

        if user == ADMIN_USER and pw == ADMIN_PASS:
            session["admin_logged_in"] = True
            flash("Вход выполнен", "success")
            return redirect(next_url)
        else:
            flash("Неверный логин или пароль", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/admin/logout")

def logout():
    session.pop("admin_logged_in", None)
    flash("Вы вышли из админки", "success")
    return redirect(url_for("login"))

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        media_type = request.form.get("media_type")
        file = request.files.get("file")

        if not file or not file.filename:
            flash("⚠️ Не выбран файл!", "error")
            return redirect(url_for("admin"))

        filename = file.filename
        url = upload_file(file, filename)
        if not url:
            flash("❌ Ошибка загрузки в облако!", "error")
            return redirect(url_for("admin"))

        # --- Добавляем в JSON ---
        if media_type == "audio":
            artist = request.form.get("artist") or "Unknown"
            genre = request.form.get("genre") or "Unknown"
            price_raw = request.form.get("price", "0")

            try:
                price = int(float(price_raw) * 100)
            except:
                price = 0

            covers = load_covers()
            covers.append({
                "filename": filename,
                "url": f"/stream/{filename}",
                "artist": artist,
                "genre": genre,
                "price": price
            })
            save_covers(covers)
            print(f"[JSON] 🎵 Добавлена запись: {filename}")

        elif media_type == "video":
            title = request.form.get("title") or filename
            videos = load_videos()
            videos.append({
                "filename": filename,
                "url": f"/stream/{filename}",
                "title": title
            })
            save_videos(videos)
            print(f"[JSON] 🎬 Добавлена запись: {filename}")

        flash(f"✅ Файл '{filename}' успешно загружен!", "success")
        return redirect(url_for("admin"))

    # Отображаем список файлов
    audios, videos = list_media()
    return render_template("admin.html", covers=audios, videos=videos, ADMIN_USER=ADMIN_USER)

@app.route("/admin/delete/<media_type>/<filename>", methods=["POST"])
def delete_media(media_type, filename):
    if not session.get("admin_logged_in"):
        flash("❌ Доступ запрещён. Войдите в админку.", "error")
        print(f"[WARN] Неавторизованный доступ к удалению: {filename}")
        return redirect(url_for("login"))

    print(f"\n=== 🗑️ УДАЛЕНИЕ ФАЙЛА ===")
    print(f"Тип: {media_type}")
    print(f"Файл: {filename}")

    # Загружаем JSON
    if media_type == "audio":
        items = load_covers()
        save_fn = save_covers
    else:
        items = load_videos()
        save_fn = save_videos

    # Проверяем, есть ли файл
    found = next((x for x in items if x["filename"] == filename), None)
    if not found:
        print(f"[ERROR] Файл '{filename}' не найден в JSON")
        flash("Файл не найден.", "error")
        return redirect(url_for("admin"))

    # Пробуем удалить из Spaces
    try:
        delete_object(filename)
        print(f"[OK] Удалено из облака: {filename}")
    except Exception as e:
        print(f"[ERROR] Ошибка при удалении из Spaces: {e}")
        flash(f"Ошибка при удалении из облака: {e}", "error")

    # Удаляем из JSON
    items = [x for x in items if x["filename"] != filename]
    save_fn(items)
    print(f"[OK] Удалено из JSON: {filename}")
    print("=========================\n")

    flash(f"✅ '{filename}' удалён!", "success")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
