from flask import (
    Flask, render_template, redirect, url_for, send_file,
    request, flash, jsonify, session, abort
)
import os, json, uuid

from flask import send_from_directory
from functools import wraps



app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "supersecret_local_change_me")

# ----- пути -----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COVERS_DIR = os.path.join("static", "covers")
COVERS_JSON = os.path.join(COVERS_DIR, "covers.json")

# ----- админ конфиг из .env -----
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "neSko567___2341")

# ----- убедимся, что папка есть -----
os.makedirs(COVERS_DIR, exist_ok=True)
if not os.path.exists(COVERS_JSON):
    with open(COVERS_JSON, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

# ----- загрузка/сохранение JSON -----
def load_covers():
    with open(COVERS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def save_covers(covers):
    with open(COVERS_JSON, "w", encoding="utf-8") as f:
        json.dump(covers, f, ensure_ascii=False, indent=2)

# ----- декоратор для защиты админ маршрутов -----
def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapped

# ======== публичная часть (index, fake-buy, download) ========

@app.route("/")
def index():
    query = request.args.get("q", "").lower()
    covers = load_covers()

    for c in covers:
        c["audio_url"] = url_for("serve_audio", filename=c["filename"])

    if query:
        covers = [c for c in covers if query in c['artist'].lower()
                  or query in c['filename'].lower()
                  or query in c['genre'].lower()]
    return render_template("index.html", covers=covers, query=query)
# одноразовые токены в памяти
download_tokens = {}

@app.route("/fake-buy/<filename>", methods=["POST"])
def fake_buy(filename):
    covers = load_covers()
    cover = next((c for c in covers if c["filename"] == filename), None)

    if not cover:
        return jsonify({"success": False, "message": "Песня не найдена!"}), 404

    token = uuid.uuid4().hex
    download_tokens[token] = filename

    return jsonify({
        "success": True,
        "message": "Оплата успешно имитирована! ✅",
        "download_url": f"/download/{token}"
    })

@app.route("/download/<token>")
def download(token):
    # если токен — это имя файла (старый маршрут), блокируем — теперь токен обязателен
    if token in [c.get("filename") for c in load_covers()]:
        return "⛔ Прямой доступ запрещён. Используй одноразовый токен.", 403

    if token not in download_tokens:
        return "⛔ Ссылка недействительна или уже использована.", 410

    filename = download_tokens.pop(token)
    file_path = os.path.join(COVERS_DIR, filename)

    if not os.path.exists(file_path):
        return "Файл не найден", 404

    return send_file(file_path, as_attachment=True)

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
@admin_required
def logout():
    session.pop("admin_logged_in", None)
    flash("Вы вышли из админки", "success")
    return redirect(url_for("login"))

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    covers = load_covers()

    if request.method == "POST":
        # добавление кавера
        artist = request.form.get("artist", "").strip()
        genre = request.form.get("genre", "").strip()
        price_raw = request.form.get("price", "0")
        try:
            price = int(float(price_raw) * 100)
        except:
            price = 0

        file = request.files.get("file")
        if not file or not file.filename:
            flash("⚠️ Не выбран файл!", "error")
            return redirect(url_for("admin"))

        filename = file.filename
        safe_path = os.path.join(COVERS_DIR, filename)

        # если файл с таким именем уже есть — переименуем, добавив суффикс
        if os.path.exists(safe_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{uuid.uuid4().hex[:6]}{ext}"
            safe_path = os.path.join(COVERS_DIR, filename)

        file.save(safe_path)

        covers.append({
            "filename": filename,
            "artist": artist or "Unknown",
            "genre": genre or "Unknown",
            "price": price
        })
        save_covers(covers)
        flash(f"✅ Кавер '{filename}' добавлен!", "success")
        return redirect(url_for("admin"))

    return render_template("admin.html", covers=covers)



@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(COVERS_DIR, filename)

@app.route("/delete/<filename>", methods=["POST"])
@admin_required
def delete_cover(filename):
    covers = load_covers()
    found = next((c for c in covers if c["filename"] == filename), None)
    if not found:
        flash("Файл не найден в списке.", "error")
        return redirect(url_for("admin"))

    # удаляем из JSON
    covers = [c for c in covers if c["filename"] != filename]
    save_covers(covers)

    # удаляем сам MP3, если существует
    file_path = os.path.join(COVERS_DIR, filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f"Файл {filename} удалён.", "success")
        else:
            flash("Файл не найден на диске, запись удалена из JSON.", "warning")
    except Exception as e:
        flash(f"Ошибка при удалении файла: {e}", "error")

    return redirect(url_for("admin"))

# ======== запуск ========
if __name__ == "__main__":
    app.run(debug=True)
