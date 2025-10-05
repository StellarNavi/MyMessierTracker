# initiallize main Flask app 

#imports
from datetime import datetime
from pathlib import Path, PurePosixPath

# for img upload
import mimetypes    
import os
import secrets

# generate unique ids for img names
import uuid         
import psycopg2
from dotenv import load_dotenv

# core Flask app functionality for requests and responses
from flask import (Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort)

# password hash
from flask_bcrypt import Bcrypt

# authentication handling                         
from flask_login import (LoginManager, UserMixin, login_user, logout_user, 
                         login_required, current_user)

from werkzeug.utils import secure_filename
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# get secret key for session cookies, security (prevents tampering) prior to loading
app.config['SECRET_KEY'] = (
    os.getenv('SECRET_KEY')             # from .env (currently how its used via 'flask run')
    or app.config.get('SECRET_KEY')     # from config 
    or secrets.token_hex(32)            # safeguard so app still runs
)

# password encryption and login
bcrypt = Bcrypt(app)                                          
login_manager = LoginManager(app)       
login_manager.login_view = 'login'      


# for testing between dev and prod
DEPLOYED = os.getenv('DEPLOYED')
if DEPLOYED == 'TRUE':
    UPLOAD_DIR = Path("/var/user_uploads").resolve()
else:
    UPLOAD_DIR = (Path(app.root_path).resolve().parent / "user_uploads").resolve()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# for the image loads within the pop-up journal entry
ALLOWED_EXT = {"jpg","jpeg","png","webp"}



# establish postgres connection and pull from env variables 
# (in gitignore for security best practice)
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

# function to allow resolving files on server outside of project path
@app.get("/files/<path:key>")
def files(key):
    target = (UPLOAD_DIR / key).resolve()
    # traversal guard: only serve files under UPLOAD_DIR
    if UPLOAD_DIR not in target.parents and target != UPLOAD_DIR:
        abort(404)
    return send_from_directory(str(UPLOAD_DIR), key)


# helpers for keys (adding)
def make_key(original_filename: str) -> str:
    ext = (Path(original_filename).suffix or "").lower()
    return str(PurePosixPath(f"{uuid.uuid4().hex}{ext}"))  # e.g. 'a1b2c3.jpg'

def save_to_uploads(file_storage, key: str) -> Path:
    dest = (UPLOAD_DIR / key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(str(dest))
    return dest

# function for db connection info for reuse
def get_db_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

# function to check for valid file types and returns a pass/fail for later use
def _allowed(filename: str) -> bool:
    # splits on '.' then lowers the extension then checks if its in the list from above
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXT

#user class for flask login interface
class User(UserMixin):
    def __init__(self, id, email, user_name, progress=None):
        # flask-login expects id to be string so pass as str
        self.id = str(id)
        self.email = email
        self.user_name = user_name
        # initialize summary of user progress, will pull from db in dashboard()
        self.progress = progress or {
            "total": 0,
            "nebulae": 0,
            "galaxies": 0,
            "star_clusters":0 
        }


# DASHBOARD PAGE -----------------------------------------------------------------------------------
# loads the 'home' screen data for catalog totals and progress stats as well as user journal entries
# like  messier object dropdown, object names, notes, etc
@app.route("/")
@login_required
def dashboard():
    user_id = str(current_user.id)
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # list of messier objects (used for dropdown)
            cur.execute("""
                SELECT id, messier_number, COALESCE(common_name,'')
                FROM public.messier_objects
                ORDER BY messier_number ASC
            """)
            objects = [{"id": str(r[0]),
                        "m_number": r[1],
                        "common_name": r[2]} for r in cur.fetchall()]

            # get number of each type for donut KPIs - this could be a hardcoded number for this use
            # case but I think it shows scalability having all data pull from the database.
            # Also if an object was reclassified into another category this way ensures the 
            # dashboard would properly update 
            cur.execute("""
                SELECT object_type, count(*)
                FROM messier_objects
                GROUP BY object_type
            """)
            rows = cur.fetchall()
            catalog_totals = {'Galaxy': 0, 'Nebula': 0, 'Star Cluster':0}
            # populates the category count for each Galaxy, Nebula & Star Cluster categories
            for category, category_count in rows:
                if category in catalog_totals:
                    catalog_totals[category] = int(category_count)
            
            # Main dataset for all journal data (sorted by latest observed_date first as default)
            cur.execute("""
                SELECT je.id,
                       mo.messier_number,
                       COALESCE(mo.common_name,'') AS name,
                       je.observed_date,
                       je.body,
                       i.file_path,
                       mo.constellation,
                       mo.object_type,
                       mo.ra_hours,
                       mo.dec_degrees,
                       mo.magnitude,
                       mo.notes as description,
                       mo.object_subtype,
                       mo.url as nasa_url,    
                       'M' || mo.messier_number::varchar || ': ' || mo.common_name as obj_title,
                       r.rarity_pct as rarity
                FROM public.journal_entries je
                JOIN public.messier_objects mo ON mo.id = je.messier_id
                LEFT JOIN public.images i ON i.id = je.image_id
                LEFT JOIN public.v_object_rarity r on mo.id = r.messier_id
                WHERE je.user_id = %s
                ORDER BY je.observed_date DESC, je.updated_at DESC
            """, (user_id,))
            # variables for Jinja/Bootstrap to pull in 
            entries = [{
                "id": str(r[0]),
                "m_number": r[1],
                "name": r[2],
                "date": r[3],
                "body": r[4],
                "img": r[5],
                "constellation": r[6],
                "type":r[7],
                "ra":r[8],
                "dec":r[9],
                "mag":r[10],
                "desc":r[11],
                "subtype":r[12],
                "nasa_url":r[13],
                "obj_title":r[14],
                "rarity":r[15] # Enahancement #2: Rarity metric
            } for r in cur.fetchall()]
            
            # ENHANCEMENT 2: implement a rarity score and use it to show the top remaining items 
            # get the users top 3 uncollected items by rarity to be used in the highcharts tooltips
            # see main_schema.sql for view structure
            # get the users top most rare items for journal tag
            # utilizes the existing entries table we just queried instead of sending additional
            # queries to the database
            rare_ids = [
                    e["id"] for e in sorted(
                        # only identifies entry as rare if less than half of users have logged it
                        (e for e in entries if e.get("rarity") is not None and e["rarity"] < 50),
                        key=lambda x: x["rarity"])[:3]
                    ]
            # order the ranks to be tagged with gold, silver, bronze later
            rare_ranks = {eid: i for i, eid in enumerate(rare_ids, start=1)} 
            
            # progress bar (top 3 overall)
            cur.execute(""" select messier_id, object_type, object, rarity_pct
                from public.v_object_rarity 
                where messier_id not in (select user_object_images.messier_id
                                        from public.user_object_images
                                        where user_object_images.user_id = %s)
                order by rarity_pct desc
                limit 3;""", (user_id,))
            capture_next = [{
                "messier_id":str(r[0]),
                "object_type":r[1], 
                "object":r[2],
                "rarity_pct":r[3]
            } for r in cur.fetchall()]
            
            # donut 1 (top 3 galxies)
            cur.execute(""" select messier_id, object_type, object, rarity_pct
                from public.v_object_rarity
                where messier_id not in (select user_object_images.messier_id
                                        from public.user_object_images
                                        where user_object_images.user_id = %s)
                and object_type = 'Galaxy'
                order by rarity_pct desc
                limit 3;""", (user_id,))
            capture_next_galaxy = [{
                "messier_id":str(r[0]),
                "object_type":r[1], 
                "object":r[2],
                "rarity_pct":r[3]
            } for r in cur.fetchall()]
            
            # donut 2 (top 3 nebulae)
            cur.execute(""" select messier_id, object_type, object, rarity_pct
                from public.v_object_rarity
                where messier_id not in (select user_object_images.messier_id
                                        from public.user_object_images
                                        where user_object_images.user_id = %s)
                and object_type = 'Nebula'
                order by rarity_pct desc
                limit 3;""", (user_id,))
            capture_next_nebula = [{
                "messier_id":str(r[0]),
                "object_type":r[1], 
                "object":r[2],
                "rarity_pct":r[3]
            } for r in cur.fetchall()]
            
            # donut 3 (top 3 star clusters)
            cur.execute(""" select messier_id, object_type, object, rarity_pct
                from public.v_object_rarity
                where messier_id not in (select user_object_images.messier_id
                                        from public.user_object_images
                                        where user_object_images.user_id = %s)
                and object_type = 'Star Cluster'
                order by rarity_pct desc
                limit 3;""", (user_id,))
            capture_next_star = [{
                "messier_id":str(r[0]),
                "object_type":r[1], 
                "object":r[2],
                "rarity_pct":r[3]
            } for r in cur.fetchall()]
            
            
            # get overall user progress numbers from database
            cur.execute("""
                SELECT mo.object_type, COUNT(*)
                FROM public.user_object_images uoi
                JOIN public.messier_objects mo ON mo.id = uoi.messier_id
                WHERE uoi.user_id = %s
                GROUP BY mo.object_type
            """, (user_id,))
            # creates dictionary (key value pairs) for count of each category
            by_type = {k: v for k, v in cur.fetchall()}
            #compute totals here, more efficient that running a seperate query
            total = sum(by_type.values())
            progress = {
                "total": total,
                "galaxies": by_type.get("Galaxy", 0),
                "nebulae": by_type.get("Nebula", 0),
                "star_clusters": by_type.get("Star Cluster", 0),
            }
    finally:
        conn.close()

    # attach progress to current_user then render template and pass data
    current_user.progress = progress
    del_error = request.args.get("del_error") == "1"
    
    return render_template("index.html", user=current_user, objects=objects, entries=entries,
                       catalog_totals=catalog_totals, del_error=del_error, 
                       capture_next=capture_next,
                       capture_next_galaxy = capture_next_galaxy, 
                       capture_next_nebula = capture_next_nebula,
                       capture_next_star = capture_next_star,
                       rare_ids=rare_ids, rare_ranks=rare_ranks)

# JOURNAL ADDITION ---------------------------------------------------------------------------------
# creates a new journal entry with an uploaded image, lightly validates the inputs, saves the file, 
# inserts the record details into various database tables. It does include some standardization like 
# upserts for ensuring that only one object id is logged per user to avoid duplicate journal entries
# however more complete CRUD opperations, update and delete, will be added later along with input 
# sanitization to prevent SQL injections
@app.route("/journal/new", methods=["POST"])
@login_required
def journal_new():
    # fields to present in pop-up
    user_id = str(current_user.id)                                  #inherent
    messier_id = request.form["messier_id"]                         #inherent
    observed_date = request.form.get("observed_date", "").strip()   #required user input
    file = request.files.get("image")                               #required user input
    body_text = request.form.get("journal_text","").strip()         #optional

    # basic validation forif file type is not allowed then display warning message  
    if not file or not file.filename or not _allowed(file.filename):
        flash("Please upload a JPG/PNG/WebP image.", "danger")
        return redirect(url_for("dashboard"))
    try:
        obs_date = datetime.strptime(observed_date, "%Y-%m-%d").date()
    except Exception:
        flash("Invalid observed date.", "danger")
        return redirect(url_for("dashboard"))

    original = secure_filename(file.filename)
    key = make_key(original)                 # e.g. 'a1b2c3.jpg'
    dest = save_to_uploads(file, key)        # writes to UPLOAD_DIR/key
    
    # determine the image type to properly render in browser, will revist in future when/if moved to
    # AWS S3 bucket: https://repost.aws/questions/QU8PZcrxbhTPq8defuJBF0fA/determine-real-file-type-
    # mime-of-an-uploaded-object-in-s3
    mime = mimetypes.guess_type(original)[0] or "application/octet-stream"
    size = dest.stat().st_size

    # write to Postgres: images > user_object_images > journal_entries
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # inserts the images metadata and ties it to the user then returns the db generated id
            cur.execute("""
                INSERT INTO public.images (user_id, file_name, file_path, 
                                           mime_type, byte_size, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (user_id, original, key, mime, size))
            img_id = cur.fetchone()[0]

            # upsert ensures that only a single image per user per object is allowed by chekcing if 
            # a row already exists and updating the image_id, but if not then it inserts
            cur.execute("""
                INSERT INTO public.user_object_images (user_id, messier_id, image_id, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id, messier_id) DO UPDATE
                SET image_id = EXCLUDED.image_id
            """, (user_id, messier_id, str(img_id)))

            # upsert journal entry, again looking for only one record per (user, object) and updates
            # the image, observed date and notes if it alreaday exists. Technically this is part of 
            # the UPDATE opeartion in CRUD but this is not intuitive and an 'edit' button should
            # be added to fully flesh this out
            cur.execute("""
                SELECT id FROM public.journal_entries
                WHERE user_id = %s AND messier_id = %s
            """, (user_id, messier_id))
            j = cur.fetchone()
            # if entry exists, update
            if j:
                cur.execute("""
                    UPDATE public.journal_entries
                    SET image_id = %s,
                        body = %s,
                        observed_date = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (str(img_id), body_text, obs_date, j[0]))
            # else insert
            else:
                cur.execute("""
                    INSERT INTO public.journal_entries
                        (user_id, messier_id, image_id, body, observed_date, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """, (user_id, messier_id, str(img_id), body_text, obs_date))

        conn.commit()
        flash("Journal entry saved!", "success")
    except Exception as e:
        if conn: conn.rollback()
        app.logger.exception("Failed to save journal entry, please try again later")
        flash("Failed to save journal entry, please try again later", "danger")
    finally:
        if conn: conn.close()
    
    # incorrect password handling for delete modal
    del_error = session.pop('del_error', None)
    # once complete return to dashboard
    return redirect(url_for("dashboard"))
    
    
    
# ENHANCEMENT THREE FUNCTIONS FOR COMPLETING CRUD OPERATIONS ***************************************
# Journal Entry Edit function
# this will allow the user to make updates to an existing journal entry (date, notes, image)
@app.route("/journal/edit", methods=["POST"])
@login_required
def journal_edit():
    user_id = str(current_user.id)
    entry_id = request.form.get("entry_id","")
    observed_date = request.form.get("observed_date","")
    body_text = request.form.get("journal_text","")
    obj_img = request.files.get("image")
    
    # handle in case there is an issues with fields
    if not entry_id:
        flash("Unable to locate record.", "danger")
        return redirect(url_for("dashboard"))
    try:
        # validity should be enforced through the calendar pop-up but handle in case of error
        obs_date = datetime.strptime(observed_date, "%Y-%m-%d").date()
    except Exception:
        flash("Invalid date entered","danger")
        return redirect(url_for("dashboard"))
    # ensure journal notes are not too long
    if len(body_text) > 6500:
        flash("Character limit reached!", "danger")
        return redirect(url_for("dashboard"))
    # check if new image loaded that its the proper extension
    new_obj_img = bool(obj_img and obj_img.filename)
    if new_obj_img and not _allowed(obj_img.filename):
        flash("Please use a valid image format: JPG/PNG/WebP.", "danger")
        return redirect(url_for("dashboard"))
    
    # placeholder
    old_file_path_abs  = None
    
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # ensure the database can find the user's entry to edit
            cur.execute("""
                SELECT je.id, je.image_id, je.messier_id, i.file_path
                FROM public.journal_entries je
                LEFT JOIN public.images i ON i.id = je.image_id
                WHERE je.id = %s AND je.user_id = %s
            """, (entry_id, user_id))
            row = cur.fetchone()
            if not row:
                flash("Entry not found.", "danger"); return redirect(url_for("dashboard"))
            _, old_img_id, messier_id, old_file_path = row

            # If replacing the image, save new file and create images row
            new_img_id = old_img_id
            if new_obj_img:
                original = secure_filename(obj_img.filename)
                key = make_key(original)
                dest = save_to_uploads(obj_img, key)

                mime = mimetypes.guess_type(original)[0] or "application/octet-stream"
                size = dest.stat().st_size

                # insert new image row for this user
                cur.execute("""
                    INSERT INTO public.images (user_id, file_name, file_path, mime_type, 
                    byte_size, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING id
                """, (user_id, original, key, mime, size))
                new_img_id = cur.fetchone()[0]

                # keep user_object_images in sync for this (user, messier)
                cur.execute("""
                    UPDATE public.user_object_images
                    SET image_id = %s
                    WHERE user_id = %s AND messier_id = %s
                """, (str(new_img_id), user_id, str(messier_id)))

                # update journal to point at new image
                cur.execute("""
                    UPDATE public.journal_entries
                    SET image_id = %s
                    WHERE id = %s AND user_id = %s
                """, (str(new_img_id), entry_id, user_id))

            # update date/notes and get updated timestamp
            cur.execute("""
                UPDATE public.journal_entries
                SET observed_date = %s,
                    body = %s,
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
            """, (obs_date, body_text, entry_id, user_id))

            # If we replaced the image, try to clean up the old image row if it became orphaned
            if new_obj_img and old_img_id:
                # is the old image still referenced anywhere?
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM public.journal_entries WHERE image_id = %s
                        UNION ALL
                        SELECT 1 FROM public.user_object_images WHERE image_id = %s
                    )
                """, (str(old_img_id), str(old_img_id)))
                still_used = cur.fetchone()[0]

                if not still_used:
                    # capture old file path then delete the DB row
                    if old_file_path:
                        # make absolute for later deletion post-commit
                        old_file_path_abs = (UPLOAD_DIR / old_file_path)
                    cur.execute("DELETE FROM public.images WHERE id = %s", (str(old_img_id),))

        conn.commit()
        flash("Journal entry updated!", "success")

    except Exception:
        if conn: conn.rollback()
        app.logger.exception("Failed to update journal entry")
        flash("Failed to update journal entry, please try again later", "danger")
    finally:
        if conn: conn.close()

    # Post-commit: best-effort filesystem delete of the *old* image file (if orphaned)
    if old_file_path_abs:
        try:
            if os.path.exists(old_file_path_abs):
                os.remove(old_file_path_abs)
        except Exception:
            app.logger.exception("Failed to delete old file %s", old_file_path_abs)

    return redirect(url_for("dashboard"))

# TODO Journal Entry Delete function ---------------------------------------------------------------
@app.route("/journal/delete", methods=["POST"])
@login_required
def journal_delete():
    user_id = str(current_user.id)
    entry_id = request.form.get("entry_id", "")

    # if there is an issue collecting the entry id then flash error and send back to dashboard
    if not entry_id:
        flash("Missing entry id.", "danger")
        return redirect(url_for("dashboard"))
    
    conn = get_db_conn()
    cur = conn.cursor()

    
    # get img id from journal entry and pass here to get the path
    # should always be unique id across users but including the user id for safety
    cur.execute("""SELECT image_id 
                   FROM public.journal_entries 
                   WHERE id = %s and user_id = %s 
                   limit 1""", (entry_id, user_id))
    img_id = cur.fetchone()[0]

    # pass image id to get the path of stored imageso it can be removed later
    cur.execute("""SELECT file_path 
                   FROM public.images 
                   WHERE id = %s and user_id = %s 
                   limit 1""", (img_id, user_id))
    img_key = cur.fetchone()[0]
    
    # DELETE ALL DATABASE RECORDS
    # delete the journal entry
    cur.execute("""DELETE 
                   FROM public.journal_entries 
                   WHERE id = %s AND user_id = %s ;""",
                (entry_id, user_id))


    # TODO remove record from user_object_images
    cur.execute("""DELETE 
                FROM public.user_object_images 
                WHERE image_id = %s AND user_id = %s ;""",
                (img_id, user_id))

    # TODO remove record from images
    cur.execute("""DELETE 
                FROM public.images 
                WHERE id = %s AND user_id = %s ;""",
                (img_id, user_id))
    conn.commit()
    

    # DELETE FROM FILE STORAGE
    # TODO remove image file from file storage
    try:
        # updated to be platform agnositic for web service deployment
        # TODO: VALIDATE
        p = (UPLOAD_DIR / img_key)
        if p.exists():
            p.unlink()
    except Exception:
        app.logger.exception("Failed to delete file %s", p)

    return redirect(url_for("dashboard"))





# FLASK LOGIN --------------------------------------------------------------------------------------
# load user from postgres by id
@login_manager.user_loader
def load_user(user_id: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, user_name FROM public.users WHERE id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return User(row[0], row[1], row[2])
    finally:
        conn.close()

# LOGIN PAGE VIEW ----------------------------------------------------------------------------------
# verifies user credentials with bcrypt on each post, once verified then sends user to dashboard.
# if already authenticated then get automatically redirected to the dashboard.
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard")) 

    error = None
    if request.method == "POST":
        # cleans email entered for cleaner lookup
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_conn()
        # checks for records in db matching the email entered
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, user_name, password_hash FROM public.users WHERE email = %s",
                    (email,)
                )
                row = cur.fetchone()
        finally:
            conn.close()

        # verify password using bcrypt hash to see if entered password post hash = db hash
        # more about bcrypt in the register function below
        if row and row[3] and bcrypt.check_password_hash(row[3], password):
            user = User(row[0], row[1], row[2])
            login_user(user, remember=bool(request.form.get("remember")))
            nxt = request.args.get("next")
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid email or password."

    return render_template("login.html", error=error)

# REGISTER PAGE VIEW -------------------------------------------------------------------------------
# if already logged in then gets redirected to dashboard
# else go through form validation and create a new account
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        # cleans email entered for cleaner lookup
        email = request.form.get("email", "").strip().lower()
        user_name = request.form.get("user_name", "").strip()
        # two password fields to confirm no keying errors
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        # basic input validation (all required)
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
                    # meaning a record was found
                    if exists:
                        error = "An account with that email already exists, please use login."
                    else:
                        # bcrypt is commonly used for securely storing passwords in databases,
                        # its used here to hash the plaintext password by mixing it with a random 
                        # value (salt) and storing it as a non-reversible UTF-8 string which will 
                        # later then be used to verify the password. It's reliable becuase it allows
                        # for multiple users to have the same password but does not generate the 
                        # same hash and is very computationally intensive to try to break.
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

# REGISTER PAGE VIEW -------------------------------------------------------------------------------
# simple reroute to login screen once logged out
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# PROFILE PAGE VIEW -------------------------------------------------------------------------------
# placeholder 
@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user)

# ABOUT PAGE VIEW -------------------------------------------------------------------------------
# simple route to a short page that provides more information about the application 
@app.route("/about")
@login_required
def about():
    return render_template("about.html", user=current_user)

# DELETE ACCOUNT PAGE VIEW -------------------------------------------------------------------------
# wip
@app.route("/account/delete", methods=["POST"])
@login_required
def account_delete():
    # pulled from delete modal password input
    pwd = request.form.get("delete_acct_password", "")
    user_id = str(current_user.id)

    # open db connection
    conn = get_db_conn()
    # placeholder for files to collect then delete
    file_paths = []
    try:
        with conn.cursor() as cur:
            # Verify password
            cur.execute("""SELECT password_hash 
                        FROM public.users WHERE id = %s""", (user_id,))
            row = cur.fetchone()
            # bad password
            if not row or not row[0] or not bcrypt.check_password_hash(row[0], pwd):
                flash("Incorrect password. Please try again.", "danger")
                session['del_error'] = "Incorrect password. Please try again"
                return redirect(url_for("dashboard", del_error=1))

            # pass userid & get image paths before deleting from table so they can be removed later
            cur.execute("SELECT file_path FROM public.images WHERE user_id = %s", (user_id,))
            img_files = [r[0] for r in cur.fetchall()]

            # delete all user data via cascades generated at schema creation, this setup properly 
            # manages the removal of records from journal_entries, user_object_images, images tables
            cur.execute("DELETE FROM public.users WHERE id = %s", (user_id,))

        # commits changes to db
        conn.commit()
        
    # if process failed, let user know and send back to dashboard page and close db connection    
    except Exception:
        if conn: conn.rollback()
        # error then shown in the delete modal setup in index.html
        return redirect(url_for("dashboard"))
    finally:
        if conn:
            conn.close()

    # then remove actual image files from storage
    for img in img_files:
        try:
            # updated to be platform agnositic for web service deployment
            # TODO: VALIDATE
            p = (UPLOAD_DIR / img)
            if p.exists():
                p.unlink()
        except Exception:
            app.logger.exception("Failed to delete file %s", img)

    # send user to the 'success' screen and logout
    logout_user()
    return render_template("post_delete.html") 


# runs the app
if __name__ == '__main__':
    app.run(debug=True)

# NTS: DONT FORGET TO RUN DOCKER!!!