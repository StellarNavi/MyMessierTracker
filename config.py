# Config vars (secret key, DB URI, etc.)
import os

# old
# class Config:
#     SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev_secret_key'
#     MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/messier_db'

# updated
class Config:
    MONGO_URI = "mongodb://localhost:27017/yourdb"
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")