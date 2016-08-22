
from datetime import datetime
from flask import request, render_template, redirect, url_for, g, session, flash, abort
from flask.ext import wtf
#from flaskext.openid import OpenID
from flask_openid import OpenID


from app import app, db
from models import User, Content, Settings, Transaction, Book
from buy_formula import evaluate_books
from utils import send_mail, easypost

from pprint import pprint

import config

oid = OpenID(app)


@app.before_request
def before_request( ):
    if session.new:
        session.permanent = True
    g.user = None
    if 'openid' in session:
        g.user = User.query.filter_by(openid=session['openid']).first( )


#=====================================================================
# Content Pages
#=====================================================================

def page( ):
    page = request.path.strip("/")
    if page == "":
        page = "index"
    content = Content.query.filter_by(name=page).first( )
    if content is None:
        content = Content( )
        content.name = page

    return render_template(page + ".html", config=config)


@app.route('/', methods=["GET", "POST"])
def index( ):
    return page( )

@app.route('/about', methods=["GET", "POST"])
def about( ):
    return page( )

@app.route('/faq', methods=["GET", "POST"])
def faq( ):
    return page( )

@app.route('/contact', methods=["GET", "POST"])
def contact( ):
    return page( )


#=====================================================================
# Book Search, Cart and Checkout
#=====================================================================

@app.route('/search', methods=["POST"])
def search( ):
    isbn = request.form.get("isbn")
    if isbn:
        isbn = isbn.replace("-", "").split( )
        (books, wont_buy, invalid_isbn) = evaluate_books(isbn)
        if invalid_isbn:
            flash("Invalid ISBN: " + ", ".join(invalid_isbn))
        if books:
            if "books" in session:
                session["books"].update(books)
                session.modified = True
            else:
                session["books"] = books
            flash("Successful added books to the cart.")
        if wont_buy:
            session["wont_buy"] = wont_buy
    else:
        flash("No ISBN specified. Type an ISBN into the search bar above and press enter.")
    return redirect(url_for("cart"))


@app.route('/cart', methods=["GET", "POST"])
def cart( ):
    #books = session.get("books", dict( ))
    #for asin, book in books.items( ):
    #    del session["books"][asin]
    if request.method == "POST":
        session.modified = True
        books = session.get("books", dict( ))
        for asin, book in books.items( ):
            quantity = int(request.form[asin].strip( ))
            if quantity < 1:
                del books[asin]
            else:
                book["quantity"] = quantity

    wont_buy = session.get("wont_buy", dict( ))
    if wont_buy:
        del session["wont_buy"]
    books = session.get("books", dict( ))
    return render_template("cart.html",
        books = books,
        wont_buy = wont_buy,
        config = config,
        total_quantity = sum(b["quantity"] for b in books.values( )),
        total_price = sum(b["quote"] * b["quantity"] for b in books.values( )),
    )

@app.route('/checkout', methods=["GET", "POST"])
def checkout( ):
    if g.user:
        # If the user is already logged in we can continue with step 2
        return redirect(url_for('checkout2'))
    form = AccountForm(request.form)
    if form.validate_on_submit( ):
        message = validate_address(form)
        if message:
            flash("Address validation failed: " + message)
        else:
            u = User( )
            form.populate_obj(u)
            u.registration_timestamp = datetime.utcnow( )
            db.session.add(u)
            db.session.commit( )
            session["seller_without_account"] = u.id
            return redirect(url_for("checkout2"))
    return render_template("checkout.html", form=form, config=config)


@app.route('/checkout2')
def checkout2( ):
    user = get_seller_with_or_without_account( )
    books = session.get("books", dict( ))
    return render_template("checkout2.html",
        user=user,
        books=books,
        total_quantity = sum(b["quantity"] for b in books.values( )),
        total_price = sum(b["quote"] * b["quantity"] for b in books.values( )),
        config=config)


@app.route('/checkout3')
def checkout3( ):
    user = get_seller_with_or_without_account( )
    settings = dict((s.name, s.value) for s in Settings.query.all( ))
    (succeed, resp) = buy_postage(settings, user)
    if succeed:
        t = Transaction( )
        t.user = user
        t.transaction_time = datetime.utcnow( )
        t.payment_method = user.payment_method
        t.price = sum(b["quote"] * b["quantity"] for b in session["books"].values( ))
        t.shipping_carrier = resp["rate"]["carrier"]
        t.shipping_service = resp["rate"]["service"]
        t.shipping_rate = float(resp["rate"]["rate"])
        t.shipping_tracking_code = resp["tracking_code"]
        t.shipping_label_file_type = resp["label_file_type"]
        t.shipping_label_url = resp["label_url"]
        t.status = "Received purchase offer"
        db.session.add(t)

        for (asin, book) in session["books"].iteritems( ):
            b = Book( )
            b.transaction = t
            b.isbn = asin
            b.price = book["quote"]
            b.quantity = book["quantity"]
            db.session.add(b)

        db.session.commit( )
        del session["books"]
        template_vars = dict(
            shipping_label_url = resp["label_url"],
            html_payment_method_info = config.cache.get("content")["payment_checkout_{}_html".format(user.payment_method.lower( ))],
            text_payment_method_info = config.cache.get("content")["payment_checkout_{}_text".format(user.payment_method.lower( ))],
            html_exchange_method_info = config.cache.get("content")["exchange_checkout_{}_html".format(user.exchange_method.replace(" ", "").lower( ))],
            text_exchange_method_info = config.cache.get("content")["exchange_checkout_{}_text".format(user.exchange_method.replace(" ", "").lower( ))],
            html_carrier_info = config.cache.get("content")["carrier_checkout_{}_html".format(t.shipping_carrier.lower( ))],
            text_carrier_info = config.cache.get("content")["carrier_checkout_{}_text".format(t.shipping_carrier.lower( ))]
        )
        send_mail("purchase", user, **template_vars)
        return render_template("checkout3.html", config=config, **template_vars)
    else:
        # XXX Shouldn't we do something, like writing this to a log?
        flash('Failed to buy the postage for your package ("{}")'.format(resp))
        return redirect(url_for('checkout2'))

def get_seller_with_or_without_account( ):
    if g.user:
        user = g.user
    else:
        seller_without_account = session.get("seller_without_account")
        if seller_without_account:
            user = User.query.get(seller_without_account)
        else:
            abort(400)
    return user

def buy_postage(s, u):
    "s=settings u=user"
    books = session["books"].values( )
    floor = lambda x: float(int(x))
    add20 = lambda x: floor(x + (x  / 100 * 20)) # We add 20% as buffer to the package dimensions
    book_stack_length = max(b["item_length"] for b in books)
    book_stack_width = sum(b["item_width"] * b["quantity"] for b in books)
    book_stack_height = max(b["item_height"] for b in books)
    book_stack_weight = floor(sum(b["item_weight"] * b["quantity"] for b in books))
    postage_buy_request = {
        'from[name]'          : u.full_name,
        'from[street1]'       : u.street1,
        'from[street2]'       : u.street2,
        'from[city]'          : u.city,
        'from[state]'         : u.state,
        'from[zip]'           : u.zip_code,
        'to[name]'        : s["address_full_name"],
        'to[phone]'       : s["address_phone"],
        'to[street1]'     : s["address_street"],
        'to[city]'        : s["address_city"],
        'to[state]'       : s["address_state"],
        'to[zip]'         : s["address_zip_code"],
        'carrier'           : config.cache["settings"]["easypost_carrier"],
        'service'           : config.cache["settings"]["easypost_carrier_service"],
        'parcel[length]'    : add20(book_stack_length),
        'parcel[width]'     : add20(book_stack_width),
        'parcel[height]'    : add20(book_stack_height),
        'parcel[weight]'    : book_stack_weight if book_stack_weight > 100.0 else 100.0,
        #'parcel[predefined_package]' : "Parcel",
    }
    pprint(postage_buy_request)
    r = easypost("postage/buy", postage_buy_request)
    j = r.json( )
    if r.status_code != 200:
        if "error" in j:
            return (False, j["error"])
        else:
            return (False, "HTTP error code: " + str(r.status_code))
    if "error" in j:
        return (False, j["error"])
    return (True, j)


#=====================================================================
# Login and Registration
#=====================================================================

@app.route('/signin', methods=['GET', 'POST'])
@oid.loginhandler
def signin( ):
    """Does the login via OpenID.  Has to call into `oid.try_login`
    to start the OpenID machinery.
    """
    # if we are already logged in, go back to were we came from
    if g.user is not None:
        return redirect(oid.get_next_url( ))

    if request.method == 'POST':
        openid = request.form.get('openid_identifier')
        if openid:
            return oid.try_login(openid, ask_for=['email', 'fullname'])

    return render_template('signin.html', next=oid.get_next_url( ), error=oid.fetch_error( ), config=config)


@oid.after_login
def create_or_login(resp):
    session['openid'] = resp.identity_url
    user = User.query.filter_by(openid=resp.identity_url).first( )
    if user is not None:
        flash(u'Successfully signed in')
        g.user = user
        return redirect(oid.get_next_url( ))
    return redirect(url_for('create_account', next=oid.get_next_url( ), full_name=resp.fullname, email_address=resp.email, openid=resp.identity_url))

@app.route('/logout')
def logout( ):
    session.pop('openid', None)
    flash(u'You have been signed out')
    return redirect(url_for("index"))


#=====================================================================
# Account
#=====================================================================

class AccountForm(wtf.Form):
    full_name = wtf.TextField(validators=[wtf.required( )])
    email_address = wtf.TextField(validators=[wtf.required( )])
    street1 = wtf.TextField(label="Street 1", validators=[wtf.required( )])
    street2 = wtf.TextField(label="Street 2")
    city = wtf.TextField(validators=[wtf.required( )])
    state = wtf.TextField(validators=[wtf.required( )])
    zip_code = wtf.TextField(validators=[wtf.required( )])
    exchange_method = wtf.SelectField(
        choices=[(x, x) for x in "Ship In|Drop Off|Pick Up".split("|")],
        validators=[wtf.required( )])
    payment_method = wtf.SelectField(
        choices=[(x, x) for x in "PayPal|Cash|Check".split("|")],
        validators=[wtf.required( )])
    university = wtf.TextAreaField( )

    def validate_payment_method(self, field):
        if self.exchange_method.data in "Drop Off|Pick Up".split("|") and self.payment_method.data != "Cash":
            raise wtf.ValidationError("We only offer the payment method Cash for the exchange methods Dropoff and Pickup")
        if self.payment_method.data == "Cash":
            allowed_zip_codes = config.cache.get("settings")["allowed_zip_codes_for_cash"].split("\n")
            zip_code = int(self.zip_code.data)
            if not self.is_allowed_zip(zip_code, allowed_zip_codes):
                raise wtf.ValidationError("The payment option Cash isn't available for your zip code.")

    def validate_zip_code(self, field):
        allowed_zip_codes = config.cache.get("settings")["allowed_zip_codes"].split("\n")
        zip_code = int(self.zip_code.data)
        if not self.is_allowed_zip(zip_code, allowed_zip_codes):
            raise wtf.ValidationError("Your zip code isn't in the allowed range.")

    def is_allowed_zip(sefl, zip_code, allowed_zip_codes):
        is_allowed = list( )
        for allowed_zip_code in allowed_zip_codes:
            if "-" in allowed_zip_code:
                start, end = allowed_zip_code.split("-")
                start = int(start.strip( ))
                end = int(end.strip( ))
                is_allowed.append(zip_code >= start and zip_code <= end)
            else:
                is_allowed.append(zip_code == int(allowed_zip_code.strip( )))
        return any(is_allowed)

    def OLD_validate_zip_code(self, field):
        #allowed_zip_codes_setting = Settings.query.filter_by(name="allowed_zip_codes").first( ) # XXX - Optimazation: Mem cache
        allowed_zip_codes_setting = config.cache.get("settings")["allowed_zip_codes"]
        allowed_zip_codes = set( )
        for x in allowed_zip_codes_setting.value.split("\n"):
            if "-" in x:
                a, b = tuple(x.split("-"))
                for c in range(int(a), int(b) + 1):
                    allowed_zip_codes.add(c)
            else:
                allowed_zip_codes.add(int(x))
        if not int(self.zip_code.data) in allowed_zip_codes:
            raise wtf.ValidationError("Your zip code isn't in the allowed range.")

    def __init__(self, *args, **kwargs):
        super(AccountForm, self).__init__(*args, **kwargs)
        """
        We can't set the 'description' at class creation because it could change after that (per admin interface)
        so we have to set it at every request. We could write the description in the code but this would be less
        flexible.
        """
        self.full_name.description = config.cache.get("content")["form_desc_full_name"]
        self.email_address.description = config.cache.get("content")["form_desc_email_address"]
        self.street1.description = config.cache.get("content")["form_desc_street1"]
        self.street2.description = config.cache.get("content")["form_desc_street2"]
        self.city.description = config.cache.get("content")["form_desc_city"]
        self.state.description = config.cache.get("content")["form_desc_state"]
        self.zip_code.description = config.cache.get("content")["form_desc_zip_code"]
        self.payment_method.description = config.cache.get("content")["form_desc_payment"]
        self.exchange_method.description = config.cache.get("content")["form_desc_exchange"]
        self.university.description = config.cache.get("content")["form_desc_university"]

def validate_address(f):
    "Returns None if everything is OK or a string with the reason what's wrong"
    data = {
        'address[street1]'  : f.street1.data,
        'address[street2]'  : f.street2.data,
        'address[city]'     : f.city.data,
        'address[state]'    : f.state.data,
        'address[zip]'      : f.zip_code.data
    }
    r = easypost("address/verify", data)
    if r.status_code != 200:
        return "HTTP error while validating address"
    r = r.json( )
    if "message" in r:
        return r["message"]
    elif "error" in r:
        return r["error"]


@app.route('/create_account', methods=['GET', 'POST'])
def create_account( ):
    if g.user is not None or 'openid' not in session:
       return redirect(url_for('index'))
    class Dummy:
        email_address = request.args.get("email_address")
        full_name = request.args.get("full_name")
    form = AccountForm(request.form, Dummy( ))
    if form.validate_on_submit( ):
        message = validate_address(form)
        if message:
            flash("Address validation failed: " + message)
        else:
            u = User( )
            form.populate_obj(u)
            u.openid = request.args.get("openid")
            u.registration_time = datetime.utcnow( )
            db.session.add(u)
            db.session.commit( )
            send_mail("registration", u)
            flash("Registration complete, Welcome! You should receive a confirmation email shortly.")
            return redirect(request.args.get("next") or url_for("account"))
    else:
        flash("Please fill out the following form to complete your registration.")
    return render_template('account.html', form=form, config=config)


@app.route('/account', methods=['GET', 'POST'])
def account( ):
    if g.user is None:
       return redirect(url_for('signin', next=url_for('account')))
    form = AccountForm(request.form, g.user)
    if form.validate_on_submit( ):
        message = validate_address(form)
        if message:
            flash("Address validation failed: " + message)
        else:
            form.populate_obj(g.user)
            db.session.add(g.user)
            db.session.commit( )

    return render_template('account.html', form=form, user=g.user, config=config)


@app.route('/transactions', methods=['GET', 'POST'])
def transactions( ):
    if g.user is None:
       return redirect(url_for('signin', next=url_for('transactions')))
    transactions = Transaction.query.filter_by(user=g.user).order_by(Transaction.transaction_time.desc( ))
    return render_template('transactions.html', user=g.user, transactions=list(transactions), config=config)

