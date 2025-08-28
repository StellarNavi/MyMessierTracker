from flask_bcrypt import Bcrypt

DB_HOST = 'localhost'
DB_PORT = 5432
DB_NAME = "messier"
DB_USER = "messier" #not ideal, can change later
DB_PASS = "messier" #not ideal, can change later

bcrypt = Bcrypt()

# example user info
email = "user@example.com"
user_name = "Test User"
password = "TestPass123!"
hashed = bcrypt.generate_password_hash(password).decode("utf-8")

# initiate db connection
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASS
)
cur = conn.cursor()


# inserts in new data for new user
cur.execute("""
INSERT INTO public.users (email, user_name, password_hash, verified_email)
VALUES (%s, %s, %s, TRUE)
ON CONFLICT (email) DO NOTHING;
""", (email, user_name, hashed))

conn.commit()
cur.close()
conn.close()

print(f"Seeded {email} / {password} successfully")