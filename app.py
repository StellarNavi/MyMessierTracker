# initiallize main Flask app entry point

#imports
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user    # testing       
import psycopg2
import os
from config import Config


app = Flask(__name__)
app.config.from_object(Config)

# setup MongoDB database
mongo = PyMongo(app)

# password encryption
bcrypt = Bcrypt(app)

# login                                             
login_manager = LoginManager(app)       # testing
login_manager.login_view = 'login'      # testing


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

#user class for login
class User(UserMixin):
    def __init__(self, id, email, user_name, progress=None): #todo - map to the view for user progress table
        self.id = str(id)          # flask-login expects stringable id so pass as str
        self.email = email
        self.user_name = user_name
        # simple summary of user progress for main page with analytics
        self.progress = progress or {
            "total": 0,
            "nebulae": 0,
            "galaxies": 0,
            "star_clusters":0
        }


# routing
@app.route("/")
@login_required
def dashboard():
    return render_template("index.html", user=current_user)

#describe how flask should  load a user from Postgres by id
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