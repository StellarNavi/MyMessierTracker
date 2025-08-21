# initiallize main Flask app entry point

#imports
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user    # testing       
import psycopg2
import os
from config import Config
import uuid, os, mimetypes
from datetime import datetime
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config.from_object(Config)

# setup MongoDB database
mongo = PyMongo(app)

# password encryption
bcrypt = Bcrypt(app)

# login                                             
login_manager = LoginManager(app)       # testing
login_manager.login_view = 'login'      # testing

# for the pop-up journal entry
ALLOWED_EXT = {"jpg","jpeg","png","webp"}
UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# establish postgres connection and pull from env variables (with gitignore for security)
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

def get_db_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

# checks for valid file type
def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXT

#user class for login
class User(UserMixin):
    def __init__(self, id, email, user_name, progress=None): #todo - map to the view for user progress table
        self.id = str(id)          # flask-login expects stringable id so pass as str
        self.email = email
        self.user_name = user_name
        # simple summary of user progress for main page with analytics   TODO - updated to db views for actuals
        self.progress = progress or {
            "total": 0,
            "nebulae": 0,
            "galaxies": 0,
            "star_clusters":0
        }



@app.route("/") # ************************ 8/20 update - current
@login_required
def dashboard():
    # fetch options for the modal/pop-up
    conn = get_db_conn()
    try:
        with conn.cursor() as cur: # get list of valid messier objects for the dropdown foruser to choose from
            cur.execute("""
                SELECT messier_number, common_name AS common_name
                FROM public.messier_objects
                ORDER BY messier_number ASC -- this ensures the list order makes sense
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    objects = [{"m_number": r[0], "common_name": r[1]} for r in rows]
    return render_template("index.html", user=current_user, objects=objects)


# function for loading a journal entry, intaking an image and ensuring there is just one image per object loaded
@app.route("/journal/new", methods=["POST"])
@login_required
def journal_new():
    user_id = int(current_user.id)
    messier_id = int(request.form["messier_id"])
    observed_date = request.form.get("observed_date", "").strip()
    journal_text = request.form.get("journal_text","").strip()
    file = request.files.get("image")

    # basic validation
    if not file or not file.filename or not _allowed(file.filename):
        flash("Please upload a JPG/PNG/WebP image.", "invalid file type")
        return redirect(url_for("dashboard"))
    try:
        obs_date = datetime.strptime(observed_date, "%Y-%m-%d").date()
    except Exception:
        flash("Invalid observed date.", "danger")
        return redirect(url_for("dashboard"))

    # save file locally under /static/uploads/<uuid>.<ext> **FOR NOW - will move to cloud in future**
    original = secure_filename(file.filename)
    ext = original.rsplit(".",1)[1].lower()
    img_id = uuid.uuid4()
    fname = f"{img_id}.{ext}"
    abs_path = os.path.join(UPLOAD_DIR, fname)
    rel_path = f"/static/uploads/{fname}"
    file.save(abs_path)

    # write to Postgres: images -> user_object_images (upsert) -> journal_entries (upsert)
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # 1) insert image row
            cur.execute("""
                INSERT INTO public.images (id, file_name, file_path, mime_type, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (str(img_id), original, rel_path, mimetypes.guess_type(original)[0] or "application/octet-stream"))

            # 2) ensure a single image per (user, object)
            # if a row already exists, update the image_id; else insert
            cur.execute("""
                SELECT id FROM public.user_object_images
                WHERE user_id = %s AND messier_id = %s
            """, (user_id, messier_id))
            row = cur.fetchone()
            if row:
                cur.execute("""
                    UPDATE public.user_object_images
                    SET image_id = %s
                    WHERE id = %s
                """, (str(img_id), row[0]))
            else:
                cur.execute("""
                    INSERT INTO public.user_object_images (id, user_id, messier_id, image_id, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (str(uuid.uuid4()), user_id, messier_id, str(img_id)))

            # 3) journal entry: one per (user, object); update if exists
            cur.execute("""
                SELECT id FROM public.journal_entries
                WHERE user_id = %s AND messier_id = %s
            """, (user_id, messier_id))
            j = cur.fetchone()
            if j:
                cur.execute("""
                    UPDATE public.journal_entries
                    SET image_id = %s,
                        journal_text = %s,
                        observed_date = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (str(img_id), journal_text, obs_date, j[0]))
            else:
                cur.execute("""
                    INSERT INTO public.journal_entries
                        (id, user_id, messier_id, image_id, body, observed_date, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (str(uuid.uuid4()), user_id, messier_id, str(img_id), journal_text, obs_date))

        conn.commit()
        flash("Journal entry saved.", "success")
    except Exception as e:
        if conn: conn.rollback()
        app.logger.exception("Failed to save journal entry")
        flash("Failed to save journal entry.", "danger")
    finally:
        if conn: conn.close()

    return redirect(url_for("dashboard"))

# load user from postgres by id
@login_manager.user_loader
def load_user(user_id: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, user_name FROM public.users WHERE id = %s", # the '%s' passes the user_id value
                (user_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return User(row[0], row[1], row[2])
    finally:
        conn.close()

# 8/12 updates - sessions for handling user login and then loading that users data
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        # return redirect(url_for("profile")) #can go to profile later via button/link
        return redirect(url_for("dashboard")) # go to dashboard after successful login

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, user_name, password_hash FROM public.users WHERE email = %s",
                    (email,)
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row and row[3] and bcrypt.check_password_hash(row[3], password):
            user = User(row[0], row[1], row[2])
            login_user(user, remember=bool(request.form.get("remember")))
            nxt = request.args.get("next")
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid email or password."

    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user_name = request.form.get("user_name", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        # basic validation
        if not email or not password or not user_name:
            error = "Email, name, and password are required."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            # check duplicate + insert
            conn = get_db_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM public.users WHERE email = %s", (email,))
                    exists = cur.fetchone()
                    if exists:
                        error = "An account with that email already exists."
                    else:
                        pwd_hash = bcrypt.generate_password_hash(password).decode("utf-8")
                        cur.execute("""
                            INSERT INTO public.users (email, user_name, password_hash, verified_email)
                            VALUES (%s, %s, %s, TRUE)
                            RETURNING id, email, user_name
                        """, (email, user_name, pwd_hash))
                        row = cur.fetchone()
                        conn.commit()
                        # auto-login new user
                        new_user = User(row[0], row[1], row[2])
                        login_user(new_user)
                        return redirect(url_for("dashboard"))
            finally:
                if 'conn' in locals():
                    conn.close()
    return render_template("register.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user)


# @app.route("/dashboard")
# @login_required
# def dashboard():
#     return render_template("profile.html", user=current_user)



import routes

# run app
if __name__ == '__main__':
    app.run(debug=True)

    # todo **************** DONT FORGET TO RUN DOCKER!!!