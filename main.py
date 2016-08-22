
from os import environ
from app import app, db

import models

#db.drop_all( )
db.create_all( )

import views
import admin

#admin.set_settings_defaults( )

if __name__ == '__main__':
    port = int(environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
