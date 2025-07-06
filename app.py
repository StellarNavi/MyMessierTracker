# initiallize main Flask app entry point

#imports
from flask import Flask
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
# from flask_login import LoginManager             **** commented out for now while testing *****
from config import Config


app = Flask(__name__)
app.config.from_object(Config)

# setup MongoDB database
mongo = PyMongo(app)

# password encryption
bcrypt = Bcrypt

# login                                             **** commented out for now while testing *****
# login_manager = LoginManager(app)
# login_manager.login_view = 'login'

import routes

# run app
if __name__ == '__main__':
    app.run(debug=True)