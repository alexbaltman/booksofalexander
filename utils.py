
from datetime import datetime
from base64 import b64encode
from flask_mail import Message
from flask.ext import wtf
from sqlalchemy.orm.session import Session
from app import mail, db
from models import Settings, EmailLog, EmailMessage

import config
import requests


def send_mail(email_type, user, **template_vars):
    sender = config.cache.get("settings")["email_send_address"]
    name = config.cache.get("settings")["email_send_name"]
    message = config.cache.get("emails")[email_type]

    # Without the folowing block we get this error:
    # InvalidRequestError: Object '<EmailMessage at 0x105eae510>' is already attached to session '1' (this is '17')
    message_session = Session.object_session(message)
    if message_session:
        message_session.expunge(message)
    db.session.add(message)

    email = Message(message.subject,
        sender = (name, sender),
        recipients = [user.email_address],
        body = message.text.format(**template_vars),
        html = message.html.format(**template_vars)
    )
    el = EmailLog( )
    el.user = user
    el.email = message
    el.time = datetime.utcnow( )
    db.session.add(el)
    db.session.commit( )

    return mail.send(email)



class HtmlLinkField(wtf.Field):

    def __init__(self, url, text, *args, **kwargs):
        self.url = url
        self.text = text
        super(HtmlLinkField, self).__init__(wtf.Field, *args, **kwargs)

    def __call__(self):
        return "<a href='{}'>{}</a>".format(self.url, self.text)


def easypost(request_type, data, easypost_api_key=None):
    if easypost_api_key is None:
        easypost_api_key = config.cache.get("settings")["easypost_api_key"]
    headers = {
        'Authorization' : 'Basic {}'.format(b64encode(easypost_api_key + ":"))
    }
    return requests.post("http://www.geteasypost.com/api/" + request_type, data=data, headers=headers)

