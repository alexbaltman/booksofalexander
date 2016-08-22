
from app import  db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    openid = db.Column(db.String(200))
    oauth = db.Column(db.String(200))
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean)

    full_name = db.Column(db.String(200))
    email_address = db.Column(db.String(200))
    zip_code = db.Column(db.String(200))
    state = db.Column(db.String(200))
    city = db.Column(db.String(200))
    street1 = db.Column(db.String(200))
    street2 = db.Column(db.String(200), nullable=True)
    exchange_method = db.Column(db.String(200))
    payment_method = db.Column(db.String(200))
    university = db.Column(db.Text)
    registration_time = db.Column(db.DateTime)

    # Required for administrative interface
    def __unicode__(self):
        return self.full_name


class Content(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True)
    content = db.Column(db.Text)

    def __unicode__(self):
        return self.name.encode("utf8")


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True)
    value = db.Column(db.Text)

    def __unicode__(self):
        return self.name


class EmailMessage(db.Model):
    __tablename__ = "email_messages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True)
    subject = db.Column(db.String(200))
    text = db.Column(db.Text)
    html = db.Column(db.Text)

    def __unicode__(self):
        return self.name


class EmailLog(db.Model):
    __tablename__ = "email_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User',
        backref=db.backref("email_log", lazy="dynamic"))
    email_id = db.Column(db.Integer, db.ForeignKey('email_messages.id'))
    email = db.relationship('EmailMessage',
        backref=db.backref("log", lazy="dynamic"))
    #email = db.relationship('EmailMessage')
    time = db.Column(db.DateTime)

    def __unicode__(self):
        return str(self.time)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User',
        backref=db.backref("transactions", lazy="dynamic"))
    transaction_time = db.Column(db.DateTime)
    payment_time = db.Column(db.DateTime)
    payment_method = db.Column(db.String(200))
    payment_identifier = db.Column(db.String(200))
    price = db.Column(db.Float)
    shipping_carrier = db.Column(db.String(200))
    shipping_service = db.Column(db.String(200))
    shipping_rate = db.Column(db.Float)
    shipping_tracking_code = db.Column(db.String(200))
    shipping_label_file_type = db.Column(db.String(200))
    shipping_label_url = db.Column(db.String(200))
    status = db.Column(db.String(1000))

    def __unicode__(self):
        return "Transaction({}, {})".format(self.user.full_name, self.transactions_time)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transcation_id = db.Column(db.Integer, db.ForeignKey('transaction.id'))
    transaction = db.relationship('Transaction',
        backref=db.backref("books", lazy="dynamic"))
    isbn = db.Column(db.String(20))
    price = db.Column(db.Integer)
    quantity = db.Column(db.Integer)

    def __unicode__(self):
        return "Book({})".format(self.isbn)
