from config import db


class CountryCategory(db.Model):
    __tablename__= "country_categories"
    id = db.Column(db.Integer,primary_key=True)
    name = db.Column(db.String(120),nullable=False,unique=True)
    audios = db.relationship("Audio",backref="category",lazy=True)
    videos = db.relationship("Video",backref="category",lazy=True)

# Аудио
class Audio(db.Model):
    __tablename__ = "audios"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(255))
    artist = db.Column(db.String(100))
    genre = db.Column(db.String(100))
    price = db.Column(db.Integer, default=0)
    thumb_url = db.Column(db.String(255))

    category_id = db.Column(db.Integer, db.ForeignKey("country_categories.id"))


# Видео
class Video(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(255))
    title = db.Column(db.String(255))

    category_id = db.Column(db.Integer, db.ForeignKey("country_categories.id"))
