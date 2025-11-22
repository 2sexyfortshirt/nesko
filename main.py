
import threading

# Заглушка для старых вызовов isAlive()
if not hasattr(threading.Thread, "isAlive"):
    threading.Thread.isAlive = threading.Thread.is_alive

from flask import (
Flask, render_template, redirect, url_for, send_file,
request, flash, jsonify, session, abort, Response
)
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
import os


# ---- Импорт моделей и конфигурации ----

from config import db
from models import Audio, Video, CountryCategory
from spaces_service import get_presigned_view_url, upload_file, delete_object, list_media, client, SPACES_BUCKET, SPACES_REGION

# ---- Создание приложения ----

app = Flask(__name__)



app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("FLASK_SECRET", "supersecret_local_change_me")

# ---- Инициализация расширений ----


db.init_app(app)
migrate = Migrate(app, db)
CORS(app)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs("data", exist_ok=True)

# ---- Конфиг администратора ----

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "neSko567___2341")

@app.route("/")
def index():
    query = request.args.get("q", "").strip().lower()

    # Загружаем данные из DO Spaces
    media_audios, media_videos = list_media()

    # Карты для быстрого доступа
    media_audio_map = {a["filename"].lower(): a for a in media_audios}
    media_video_map = {v["filename"].lower(): v for v in media_videos}

    # Загружаем все страны
    categories = CountryCategory.query.all()
    result = []

    for cat in categories:
        cat_data = {
            "name": cat.name,
            "audios": [],
            "videos": []
        }

        # ---------- АУДИО ----------
        for a in cat.audios:
            key = a.filename.lower()
            m = media_audio_map.get(key, {})

            item = {
                "filename": a.filename,
                "url": a.url or m.get("url"),
                "artist": a.artist,
                "genre": a.genre,
                "price": a.price,
                "thumb_url": a.thumb_url or m.get("thumb_url"),
            }

            # Поиск
            if query:
                if query not in a.filename.lower() \
                and (not a.artist or query not in a.artist.lower()) \
                and (not a.genre or query not in a.genre.lower()):
                    continue

            cat_data["audios"].append(item)

        # ---------- ВИДЕО ----------
        for v in cat.videos:
            key = v.filename.lower()
            m = media_video_map.get(key, {})

            item = {
                "filename": v.filename,
                "url": v.url or m.get("url"),
                "title": v.title,
            }

            # Поиск
            if query:
                if query not in v.filename.lower() \
                and (not v.title or query not in v.title.lower()):
                    continue

            cat_data["videos"].append(item)

        result.append(cat_data)

    # Флаги
    country_code = {
        "Россия": "ru",
        "Турция": "tr",
        "США": "us",
        "Германия": "de",
        "Франция": "fr",
        "Италия": "it",
        "Испания": "es",
        "Португалия": "pt",
        "Украина": "ua",
        "Казахстан": "kz",
        "Беларусь": "by",
        "Польша": "pl",
        "Чехия": "cz",
        "Словакия": "sk",
        "Сербия": "rs",
        "Хорватия": "hr",
        "Босния и Герцеговина": "ba",
        "Словения": "si",
        "Швейцария": "ch",
        "Австрия": "at",
        "Нидерланды": "nl",
        "Бельгия": "be",
        "Люксембург": "lu",
        "Великобритания": "gb",
        "Ирландия": "ie",
        "Дания": "dk",
        "Швеция": "se",
        "Норвегия": "no",
        "Финляндия": "fi",
        "Эстония": "ee",
        "Латвия": "lv",
        "Литва": "lt",
        "Грузия": "ge",
        "Армения": "am",
        "Азербайджан": "az",
        "Узбекистан": "uz",
        "Таджикистан": "tj",
        "Киргизия": "kg",
        "Туркменистан": "tm",
        "Китай": "cn",
        "Япония": "jp",
        "Южная Корея": "kr",
        "Индия": "in",
        "Пакистан": "pk",
        "Афганистан": "af",
        "Иран": "ir",
        "Ирак": "iq",
        "Саудовская Аравия": "sa",
        "ОАЭ": "ae",
        "Катар": "qa",
        "Бахрейн": "bh",
        "Кувейт": "kw",
        "Египет": "eg",
        "Марокко": "ma",
        "Тунис": "tn",
        "Алжир": "dz",
        "ЮАР": "za",
        "Бразилия": "br",
        "Аргентина": "ar",
        "Чили": "cl",
        "Мексика": "mx",
        "Канада": "ca",
        "Австралия": "au",
        "Новая Зеландия": "nz",
        "Болгария":"bg"
    }

    return render_template(
        "index.html",
        categories=result,
        query=query,
        country_code=country_code
    )

download_tokens = {}
from flask_cors import cross_origin
@cross_origin()
@app.route("/stream/<path:key>")
def stream(key):
    try:
        obj = client.get_object(Bucket=SPACES_BUCKET, Key=key)
        file_size = obj['ContentLength']
        range_header = request.headers.get('Range')

        if range_header:
            # Safari (и другие браузеры) отправляют Range-заголовок, например: "bytes=0-"
            byte1, byte2 = 0, None
            m = range_header.replace("bytes=", "").split("-")
            if m[0]:
                byte1 = int(m[0])
            if len(m) > 1 and m[1]:
                byte2 = int(m[1])
            length = (byte2 or file_size - 1) - byte1 + 1

            obj = client.get_object(
                Bucket=SPACES_BUCKET,
                Key=key,
                Range=f"bytes={byte1}-{byte2 or file_size - 1}"
            )

            return Response(
                obj["Body"].read(),
                206,
                mimetype="video/mp4",
                content_type="video/mp4",
                direct_passthrough=True,
                headers={
                    "Content-Range": f"bytes {byte1}-{byte2 or file_size - 1}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                }
            )

        # Если Range не указан (например, аудио)
        return Response(
            obj["Body"].read(),
            200,
            mimetype="audio/mpeg" if key.endswith(".mp3") else "video/mp4",
            headers={"Accept-Ranges": "bytes"}
        )

    except client.exceptions.NoSuchKey:
        abort(404)
import secrets

@app.route("/fake-buy/<path:filename>", methods=["POST"])
def fake_buy(filename):
    audio = Audio.query.filter_by(filename=filename).first()

    if not audio:
        return jsonify({"success": False, "error": "Файл не найден"}), 404

    # создаём одноразовый токен
    token = secrets.token_urlsafe(16)
    download_tokens[token] = filename

    return jsonify({
        "success": True,
        "download_url": f"/download/{token}"
    })
@app.route("/download/<token>")
def download(token):
    if token not in download_tokens:
        return "⛔ Ссылка недействительна или уже использована.", 410

    filename = download_tokens.pop(token)

    # проверяем в БД
    audio = Audio.query.filter_by(filename=filename).first()
    if not audio:
        return "Файл не найден", 404

    # создаём временную ссылку
    presigned_url = get_presigned_view_url(filename, expires_in=3600)

    return redirect(presigned_url)

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

    file = None  # Объявляем заранее

    if request.method == "POST":
        if 'file' in request.files:
            file = request.files.get("file")
        if not file or not file.filename:
            flash("⚠️ Не выбран файл!", "error")
            return redirect(url_for("admin"))

        media_type = request.form.get("media_type")
        filename = secure_filename(file.filename)
        url = upload_file(file, filename)
        if not url:
            flash("❌ Ошибка загрузки в облако!", "error")
            return redirect(url_for("admin"))

        try:
            category_id = int(request.form.get("category_id"))
        except (TypeError, ValueError):
            category_id = None

        # Обложка
        thumb_url = None
        thumb_file = request.files.get("thumb")
        if thumb_file and thumb_file.filename:
            thumb_name = secure_filename(thumb_file.filename)
            save_path = os.path.join("static", "covers", thumb_name)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            thumb_file.save(save_path)
            thumb_url = f"/static/covers/{thumb_name}"

        if media_type == "audio":
            artist = request.form.get("artist") or "Unknown"
            genre = request.form.get("genre") or "Unknown"
            try:
                price = int(float(request.form.get("price", "0")) * 100)
            except:
                price = 0

            new_audio = Audio(
                filename=filename,
                url=url,
                artist=artist,
                genre=genre,
                price=price,
                thumb_url=thumb_url,
                category_id=category_id
            )
            db.session.add(new_audio)

        elif media_type == "video":
            title = request.form.get("title") or filename
            new_video = Video(
                filename=filename,
                url=url,
                title=title,
                category_id=category_id
            )
            db.session.add(new_video)

        db.session.commit()
        flash(f"✅ Файл '{filename}' добавлен в базу!", "success")
        return redirect(url_for("admin"))

    # --- Рендеринг страницы ---
    audios, videos = list_media()
    categories_map = {c.id: c.name for c in CountryCategory.query.all()}

    for a in audios:
        a['category_name'] = categories_map.get(a.get('category_id'), 'Без категории')
    for v in videos:
        v['category_name'] = categories_map.get(v.get('category_id'), 'Без категории')

    categories = CountryCategory.query.all()

    return render_template(
        "admin.html",
        covers=audios,
        videos=videos,
        ADMIN_USER=ADMIN_USER,
        categories=categories
    )

@app.route("/admin/category/add", methods=["POST"])
def add_category():
    if not session.get("admin_logged_in"):
        return jsonify({"success": False, "message": "Не авторизован"}), 401

    name = request.form.get("category_name", "").strip()
    if not name:
        return jsonify({"success": False, "message": "Название категории не может быть пустым!"})

    new_cat = CountryCategory(name=name)
    db.session.add(new_cat)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Категория добавлена!",
        "category": {"id": new_cat.id, "name": new_cat.name}
    })

@app.route("/admin/category/delete", methods=["POST"])
def delete_category():
    if not session.get("admin_logged_in"):
        return jsonify({"success": False, "message": "Не авторизован"}), 401

    try:
        cat_id = int(request.form.get("category_id"))
        cat = CountryCategory.query.get(cat_id)

        if not cat:
            return jsonify({"success": False, "message": "Категория не найдена!"})

        db.session.delete(cat)
        db.session.commit()
        return jsonify({"success": True, "message": "Категория удалена!", "category_id": cat_id})
    except Exception as e:
        return jsonify({"success": False, "message": "Ошибка удаления категории!"})

@app.route("/admin/delete/<media_type>/<filename>", methods=["POST"])
def delete_media(media_type, filename):
    if not session.get("admin_logged_in"):
        return jsonify({"success": False, "message": "Доступ запрещён"}), 401

    if media_type == "audio":
        record = Audio.query.filter_by(filename=filename).first()
    elif media_type == "video":
        record = Video.query.filter_by(filename=filename).first()
    else:
        return jsonify({"success": False, "message": "Неверный тип файла"})

    if not record:
        return jsonify({"success": False, "message": "Файл не найден в базе"})

    try:
        delete_object(filename)  # удаляем из Spaces
    except Exception as e:
        return jsonify({"success": False, "message": f"Ошибка удаления из облака: {e}"})

    # удаляем локальную обложку для аудио
    if media_type == "audio" and record.thumb_url and record.thumb_url.startswith("/static/"):
        local_path = "." + record.thumb_url
        if os.path.exists(local_path):
            os.remove(local_path)

    # удаляем запись из БД
    db.session.delete(record)
    db.session.commit()

    return jsonify({"success": True, "message": f"'{filename}' удалён!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

