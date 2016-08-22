
from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flaskext.kvsession import KVSessionExtension
from simplekv.db.sql import SQLAlchemyStore


app = Flask(__name__, static_url_path='')
app.config.from_object("config")
db = SQLAlchemy(app)
mail = Mail(app)
session_store = SQLAlchemyStore(db.engine, db.metadata, 'sessions')
kvs = KVSessionExtension(session_store, app)
kvs.cleanup_sessions( )
