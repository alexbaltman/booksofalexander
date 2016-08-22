
from os import environ
from os.path import dirname, realpath
from datetime import timedelta


ON_HEROKU = True if "HEROKU_POSTGRESQL_ROSE_URL" in environ else False

PROJECT_ROOT = dirname(realpath(__file__))
DEBUG = False if ON_HEROKU else True
DEBUG = True
TRAP_BAD_REQUEST_ERRORS = DEBUG
SECRET_KEY = "XXXXX"
PERMANENT_SESSION_LIFETIME = timedelta(days=30) # How long a session should be valid

if ON_HEROKU:
    SQLALCHEMY_DATABASE_URI = environ["HEROKU_POSTGRESQL_ROSE_URL"]
    SQLALCHEMY_POOL_SIZE = 5
    SQLALCHEMY_POOL_TIMEOUT = 10
else:
    SQLALCHEMY_DATABASE_URI = "sqlite:////Users/dah/Projects/FreeLancing/TextBookWebsite/data/textbooksite_testdb.sqlite"
    SQLALCHEMY_ECHO = DEBUG

MWS_ACCESS_KEY = "XXXXX"
MWS_SECRET_KEY = "XXXXX"
MWS_MERCHANT_ID = "XXXXX"
MWS_MARKETPLACE_ID = "XXXXX"

# Flask-Mail
MAIL_USERNAME = "XXXXX"
MAIL_PASSWORD = "XXXXX"
MAIL_PORT = 587
MAIL_SERVER = "smtp.mailgun.org"

# gunicorn config

workers = 3
debug = DEBUG
timeout = 60 * 5
bind = "0.0.0.0:{0}".format(environ.get("PORT", 5000))

#def post_fork(server, worker):
#    from setup import register_everything
#    register_everything( )
