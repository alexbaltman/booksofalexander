
from flask import request, render_template, g, session, flash, Response
from flask.ext import admin, wtf
from flask.ext.admin.contrib import sqlamodel
from flask.ext.admin.actions import action
from jinja2 import Markup

from app import app, db
from models import User, Content, Settings, EmailMessage, EmailLog, Transaction, Book
from utils import HtmlLinkField, send_mail

import config
import csv
import os
import bmemcached

#-------------------------------------------------------------------
# Caching admin settings
#-------------------------------------------------------------------

#config.cache = dict( )
config.cache = bmemcached.Client(
    servers=[os.environ.get('MEMCACHEDCLOUD_SERVERS')],
    username=os.environ.get('MEMCACHEDCLOUD_USERNAME'),
    password=os.environ.get('MEMCACHEDCLOUD_PASSWORD')
)
config.cache.set("settings", dict((s.name, s.value) for s in Settings.query.all( )))
config.cache.set("emails", dict((e.name, e) for e in EmailMessage.query.all( )))
config.cache.set("content", dict((c.name, c.content) for c in Content.query.all( )))

#-------------------------------------------------------------------
# Authentication
#-------------------------------------------------------------------

class Auth(object):
    def is_accessible(self):
        #return True # TODO: delete
        return g.user is not None and g.user.is_admin

class MyBaseView(Auth, admin.BaseView): pass
class MyModelView(Auth, sqlamodel.ModelView): pass


#-------------------------------------------------------------------
# Views
#-------------------------------------------------------------------

from tempfile import mkdtemp
from os import mkdir
from os.path import join as path_join
from shutil import make_archive, rmtree
class AdminIndexView(Auth, admin.AdminIndexView):

    @admin.expose('/')
    def index(self):
        return self.render('admin/index.html')

    @admin.expose('/export')
    def export(self):
        base = mkdtemp( )
        data = path_join(base, "data")
        mkdir(data)
        try:
            for model in (User, Content, Settings, EmailMessage, EmailLog, Transaction, Book):
                columns = [c.name for c in model.__mapper__.columns]
                def rows( ):
                    for r in model.query:
                        yield [getattr(r, c) for c in columns]
                with open(path_join(data, model.__name__ + ".csv"), "w") as out:
                    o = csv.writer(out)
                    o.writerow(columns)
                    o.writerows(rows( ))
            zip = make_archive(path_join(base, "database_exort"), "zip", data)
            return Response(open(zip), mimetype="application/zip")
        finally:
            rmtree(base)




class GeneralSettingsForm(wtf.Form):
    buy_formula_number_of_used_offers = wtf.TextField(label="How many offers in the used market should a book have?", validators=[wtf.required( )])
    buy_formula_seller_to_consider = wtf.TextField(label="How many of the lowest priced sellers should be considered?", validators=[wtf.required( )])
    buy_formula_number_of_ratings = wtf.TextField(label="How many ratings should a seller have at least?", validators=[wtf.required( )])
    buy_formula_customer_satisfaction = wtf.TextField(label="What customer satisfaction should a seller have at least?", validators=[wtf.required( )])
    buy_formula_quoted_percantage = wtf.TextField(label="What percent of the chosen seller's price should be quoted?", validators=[wtf.required( )])

    address_full_name = wtf.TextField(label="Full Name", validators=[wtf.required( )])
    address_zip_code = wtf.TextField(label="Zip Code", validators=[wtf.required( )])
    address_state = wtf.TextField(label="State", validators=[wtf.required( )])
    address_city = wtf.TextField(label="City", validators=[wtf.required( )])
    address_street = wtf.TextField(label="Street", validators=[wtf.required( )])
    address_phone = wtf.TextField(label="Phone", description="Only numbers, no special characters", validators=[wtf.required( )])

    easypost_api_key = wtf.TextField(label="API Key", validators=[wtf.required( )])
    easypost_carrier = wtf.TextField(label="Carrier", validators=[wtf.required( )])
    easypost_carrier_service = wtf.TextField(label="Carrier Service", validators=[wtf.required( )])

    email_send_address = wtf.TextField(label="Sender Address", validators=[wtf.required( )])
    email_send_name = wtf.TextField(label="Sender Name", validators=[wtf.required( )])

    img_logo = wtf.TextField(label="Logo", validators=[wtf.required( )])
    img_banner_left = wtf.TextField(label="Banner Left Side", validators=[wtf.required( )])
    img_banner_right = wtf.TextField(label="Banner Right Side", validators=[wtf.required( )])
    img_about = wtf.TextField(label="About Image", validators=[wtf.required( )])

    allowed_zip_codes = wtf.TextAreaField(
        label="Allowed zip codes", description="One zip code or range per line. Define a range with a dash: 1-3", validators=[wtf.required( )])
    allowed_zip_codes_for_cash = wtf.TextAreaField(
        label="Allowed zip codes for cash payment", description="One zip code or range per line. Define a range with a dash: 1-3", validators=[wtf.required( )])

    field_sets = (
        ("Buy Formula", """buy_formula_number_of_used_offers buy_formula_seller_to_consider buy_formula_number_of_ratings
                           buy_formula_customer_satisfaction buy_formula_quoted_percantage"""),
        ("Shipping Address", "address_full_name address_zip_code address_state address_city address_street address_phone"),
        ("EasyPost", "easypost_api_key easypost_carrier easypost_carrier_service"),
        ("Email Options", "email_send_address email_send_name"),
        ("Images", "img_logo img_banner_left img_banner_right img_about"),
        ("Misc", "allowed_zip_codes allowed_zip_codes_for_cash"),
    )

class SettingsView(MyBaseView):

    @admin.expose('/', methods=["GET", "POST"])
    def index(self):
        settings = Settings.query.all( ) # XXX: Cache
        form = GeneralSettingsForm(request.form, **dict((s.name, s.value) for s in settings))
        if form.validate_on_submit( ):
            settings = dict((s.name, s) for s in settings)
            fields = " ".join(fs for (n, fs) in GeneralSettingsForm.field_sets).split( )
            for name in fields:
                s = settings.get(name, Settings( ))
                s.name = name
                s.value = getattr(form, name).data
                db.session.add(s)
            db.session.commit( )
            config.cache.set("settings", dict((s.name, s.value) for s in Settings.query.all( )))

        return self.render('admin/settings.html', form=form)

class EmailMessageForm(wtf.Form):
    registration_email_subject = wtf.TextField(label="Subject", validators=[wtf.required( )])
    registration_email_text = wtf.TextAreaField(label="Text")
    registration_email_html = wtf.TextAreaField(label="HTML")

    purchase_email_subject = wtf.TextField(label="Subject", validators=[wtf.required( )])
    purchase_email_text = wtf.TextAreaField(label="Text")
    purchase_email_html = wtf.TextAreaField(label="HTML")

    packageReceived_email_subject = wtf.TextField(label="Subject", validators=[wtf.required( )])
    packageReceived_email_text = wtf.TextAreaField(label="Text")
    packageReceived_email_html = wtf.TextAreaField(label="HTML")

    badQuality_email_subject = wtf.TextField(label="Subject", validators=[wtf.required( )])
    badQuality_email_text = wtf.TextAreaField(label="Text")
    badQuality_email_html = wtf.TextAreaField(label="HTML")

    moneySent_email_subject = wtf.TextField(label="Subject", validators=[wtf.required( )])
    moneySent_email_text = wtf.TextAreaField(label="Text")
    moneySent_email_html = wtf.TextAreaField(label="HTML")

    pickupTimeRequest_email_subject = wtf.TextField(label="Subject", validators=[wtf.required( )])
    pickupTimeRequest_email_text = wtf.TextAreaField(label="Text")
    pickupTimeRequest_email_html = wtf.TextAreaField(label="HTML")

    transactionCanceled_email_subject = wtf.TextField(label="Subject", validators=[wtf.required( )])
    transactionCanceled_email_text = wtf.TextAreaField(label="Text")
    transactionCanceled_email_html = wtf.TextAreaField(label="HTML")

    field_sets = (
        ("Registration email", "registration_email_subject registration_email_text registration_email_html"),
        ("Purchase email", "purchase_email_subject purchase_email_text purchase_email_html"),
        ("Package Received email", "packageReceived_email_subject packageReceived_email_text packageReceived_email_html"),
        ("Bad Quality email", "badQuality_email_subject badQuality_email_text badQuality_email_html"),
        ("Money Sent email", "moneySent_email_subject moneySent_email_text moneySent_email_html"),
        ("Pickup Time Request email", "pickupTimeRequest_email_subject pickupTimeRequest_email_text pickupTimeRequest_email_html"),
        ("Transaction Canceled email", "transactionCanceled_email_subject transactionCanceled_email_text transactionCanceled_email_html"),
    )

class EmailMessageView(MyBaseView):

    @admin.expose('/', methods=["GET", "POST"])
    def index(self):
        messages =  dict((m.name, m) for m in EmailMessage.query.all( )) # XXX: Cache
        defaults = dict( )
        email_message_form_fields = " ".join(fs for (n, fs) in EmailMessageForm.field_sets).split( )
        for field in email_message_form_fields:
            message, _, attr = tuple(field.split("_", 2))
            defaults[field] = getattr(messages[message], attr)
        form = EmailMessageForm(request.form, **defaults)
        if form.validate_on_submit( ):
            for field in email_message_form_fields:
                message, _, attr = tuple(field.split("_", 2))
                setattr(messages[message], attr, getattr(form, field).data)
            for m in messages.values( ):
                db.session.add(m)
            db.session.commit( )
            config.cache.set("emails", dict((e.name, e) for e in EmailMessage.query.all( )))

        return self.render('admin/email_messages.html', form=form)

class ContentForm(wtf.Form):
    html_checkout_info = "As HTML code. Is used after the ckeckout and in the HTML version of the confirmation email"
    text_checkout_info = "As text. Is used in the text version of the confirmation email"

    form_desc_full_name = wtf.TextAreaField(label="Full Name")
    form_desc_email_address = wtf.TextAreaField(label="Email Address")
    form_desc_street1 = wtf.TextAreaField(label="Street 1")
    form_desc_street2 = wtf.TextAreaField(label="Street 2")
    form_desc_city = wtf.TextAreaField(label="City")
    form_desc_state = wtf.TextAreaField(label="State")
    form_desc_zip_code = wtf.TextAreaField(label="Zip Code")
    form_desc_payment = wtf.TextAreaField(label="Payment Method")
    form_desc_exchange = wtf.TextAreaField(label="Exchange Method")
    form_desc_university = wtf.TextAreaField(label="University")

    payment_checkout_paypal_html = wtf.TextAreaField(label="PayPal Checkout (HTML)", description=html_checkout_info)
    payment_checkout_paypal_text = wtf.TextAreaField(label="PayPal Checkout (text)", description=text_checkout_info)
    payment_checkout_cash_html = wtf.TextAreaField(label="Cash Checkout (HTML)", description=html_checkout_info)
    payment_checkout_cash_text = wtf.TextAreaField(label="Cash Checkout (text)", description=text_checkout_info)
    payment_checkout_check_html = wtf.TextAreaField(label="Check Checkout (HTML)", description=html_checkout_info)
    payment_checkout_check_text = wtf.TextAreaField(label="Check Checkout (text)", description=text_checkout_info)

    exchange_checkout_shipin_html = wtf.TextAreaField(label="Ship-In Checkout (HTML)", description=html_checkout_info)
    exchange_checkout_shipin_text = wtf.TextAreaField(label="Ship-In Checkout (text)", description=text_checkout_info)
    exchange_checkout_dropoff_html = wtf.TextAreaField(label="Drop-Off Checkout (HTML)", description=html_checkout_info)
    exchange_checkout_dropoff_text = wtf.TextAreaField(label="Drop-Off Checkout (text)", description=text_checkout_info)
    exchange_checkout_pickup_html = wtf.TextAreaField(label="Pick-Up Checkout (HTML)", description=html_checkout_info)
    exchange_checkout_pickup_text = wtf.TextAreaField(label="Pick-Up Checkout (text)", description=text_checkout_info)

    carrier_checkout_usps_html = wtf.TextAreaField(label="USPS Checkout (HTML)", description=html_checkout_info)
    carrier_checkout_usps_text = wtf.TextAreaField(label="USPS Checkout (text)", description=text_checkout_info)

    field_sets = (
        ("Payment Methods",  """payment_checkout_paypal_html payment_checkout_paypal_text payment_checkout_cash_html
                                payment_checkout_cash_text payment_checkout_check_html payment_checkout_check_text"""),
        ("Exchange Methods", """exchange_checkout_shipin_html exchange_checkout_shipin_text exchange_checkout_dropoff_html
                                exchange_checkout_dropoff_text exchange_checkout_pickup_html exchange_checkout_pickup_text"""),
        ("Carriers", "carrier_checkout_usps_html carrier_checkout_usps_text"),
        ("Form Fields Description (Everything as HTML)", """
             form_desc_full_name form_desc_email_address form_desc_street1 form_desc_street2 form_desc_city form_desc_state form_desc_zip_code
             form_desc_payment form_desc_exchange form_desc_university"""),
    )

class ContentView(MyBaseView):

    @admin.expose('/', methods=["GET", "POST"])
    def index(self):
        content = dict((c.name, c.content) for c in Content.query.all( )) # XXX: Cache
        form = ContentForm(request.form, **content)
        if form.validate_on_submit( ):
            content = dict((c.name, c) for c in Content.query.all( )) # XXX: Cache
            fields = " ".join(fs for (n, fs) in ContentForm.field_sets).split( )
            for name in fields:
                c = content.get(name, Content( ))
                c.name = name
                c.content = getattr(form, name).data
                db.session.add(c)
            db.session.commit( )
            config.cache.set("content", dict((c.name, c.content) for c in Content.query.all( )))

        return self.render('admin/content.html', form=form)

class DocsView(MyBaseView):

    @admin.expose('/', methods=["GET", "POST"])
    def index(self):
        return self.render('admin/docs.html')

#-------------------------------------------------------------------
# Model Views
#-------------------------------------------------------------------

class UserAdmin(MyModelView):
    columns = 'full_name email_address zip_code state city street1 street2 exchange_method payment_method'.split( )
    column_list = columns
    column_searchable_list = columns
    column_filters = columns
    #inline_models = (Transaction,)
    form_args = dict(
        full_name = dict(validators=[wtf.required()]),
        email_address = dict(validators=[wtf.required()]),
        zip_code = dict(validators=[wtf.required()]),
        state = dict(validators=[wtf.required()]),
        city = dict(validators=[wtf.required()]),
        street1 = dict(validators=[wtf.required()]),
        street2 = dict(validators=[]),
        exchange_method = dict(validators=[wtf.required()]),
        payment_method = dict(validators=[wtf.required()]),
    )

    def __init__(self, session, *args, **kwargs):
        super(UserAdmin, self).__init__(User, session, *args, **kwargs)

    _list_formatters = dict(
        payment_method = lambda model, name: Markup("<a href='foo'>foo</a>")
    )
    _column_formatters = dict(
        payment_method = lambda context, model, name: Markup("<a href='foo'>foo</a>")
    )

    def _get_form(self):
        form = super(UserAdmin, self).get_form( )
        email = form.email_address.data
        #form.email_log = HtmlLinkField("/admin/email_log/?flt1_0=Registration", "View the email log")
        form.email_log = HtmlLinkField(url_for("emaillogadmin.index", flt1_20=email), "View the email log")
        return form


class ContentAdmin(MyModelView):
    can_create = False
    can_delete = False
    column_list = ["name"]
    #excluded_column_list = ["content"]
    sortable_columns = ["name"]
    form_args = dict(
        name = dict(validators=[wtf.required()]),
        content = dict(validators=[wtf.required()])
    )

    def __init__(self, session, *args, **kwargs):
        super(ContentAdmin, self).__init__(Content, session, *args, **kwargs)


class EmailLogAdmin(MyModelView):
    columns = "email user time".split( )
    can_create = False
    can_delete = False
    column_list = columns
    column_filters = columns
    #inline_models = (User,)
    #hide_backrefs = False
    #searchable_columns = (EmailMessage.name,)
    #column_filters = columns

    def __init__(self, session, *args, **kwargs):
        # Just call parent class with predefined model.
        super(EmailLogAdmin, self).__init__(EmailLog, session, *args, **kwargs)

class TransactionAdmin(MyModelView):
    columns = "user transaction_time".split( )
    can_create = False
    can_delete = False
    column_list = columns
    column_filters = columns
    inline_models = (Book,)

    def __init__(self, session, *args, **kwargs):
        # Just call parent class with predefined model.
        super(TransactionAdmin, self).__init__(Transaction, session, *args, **kwargs)

    def send_mail(self, msg, ids):
        transaction = Transaction.query.get(ids[0])
        user = transaction.user
        send_mail(msg, user,
            shipping_label_url = transaction.shipping_label_url,
            html_payment_method_info = config.cache.get("content")["payment_checkout_{}_html".format(user.payment_method.lower( ))],
            text_payment_method_info = config.cache.get("content")["payment_checkout_{}_text".format(user.payment_method.lower( ))],
            html_exchange_method_info = config.cache.get("content")["exchange_checkout_{}_html".format(user.exchange_method.replace(" ", "").lower( ))],
            text_exchange_method_info = config.cache.get("content")["exchange_checkout_{}_text".format(user.exchange_method.replace(" ", "").lower( ))],
            html_carrier_info = config.cache.get("content")["carrier_checkout_{}_html".format(transaction.shipping_carrier.lower( ))]
        )
        flash("Email sent")

    @action("send_email_package_received", "Send Package Received email")
    def send_email_package_received(self, ids):
        return self.send_mail("packageReceived", ids)

    @action("send_email_bad_quality", "Send Bad Quality email")
    def send_email_bad_quality(self, ids):
        return self.send_mail("badQuality", ids)

    @action("send_email_money_sent", "Send Money Sent email")
    def send_email_money_sent(self, ids):
        return self.send_mail("moneySent", ids)

    @action("send_email_pickup_time_request", "Send Pickup Time Request email")
    def send_email_package_pickup_time_request(self, ids):
        return self.send_mail("pickupTimeRequest", ids)

    @action("cancel_transaction", "Cancel Transaction")
    def cancel_transaction(self, ids):
        ret = self.send_mail("transactionCanceled", ids)
        transaction = Transaction.query.get(ids.pop( ))
        transaction.status = "canceled"
        db.session.add(transaction)
        db.session.commit( )
        return ret

#=====================================================================
# Setup
#=====================================================================

def set_settings_defaults( ):

    defaults = """
        buy_formula_number_of_used_offers = 7
        buy_formula_seller_to_consider = 5
        buy_formula_number_of_ratings = 65
        buy_formula_customer_satisfaction = 89
        buy_formula_quoted_percantage = 53
        email_send_address = tbw@obyz.de
        email_send_name = Foo
        easypost_api_key = XXXXX
        easypost_carrier = USPS
        easypost_carrier_service = Express
        address_full_name = Foo Bar
        address_zip_code = 10001
        address_state = New York
        address_city = New York
        address_street = 120 W 29th Street APT 2
        address_phone = 2125377176
        allowed_zip_codes = 1-1000000
        allowed_zip_codes_for_cash = 1-1000000
        img_logo = /img/logo_croped.png
        img_banner_left = /img/banner-left.jpeg
        img_banner_right = /img/banner-right.jpeg
        img_about = /img/aboutus_image.jpg
    """

    for default in defaults.strip( ).split("\n"):
        (name, value) = default.strip( ).split(" = ")
        s = Settings.query.filter_by(name=name).first( )
        if s is not None:
            continue
        s = Settings( )
        s.name = name
        s.value =  value
        db.session.add(s)
    db.session.commit( )

    # Email messages
    defaults = """
        registration subject text html
        purchase subject text:{shipping_label_url} html:{shipping_label_url}
        packageReceived subject text:{shipping_label_url} html:{shipping_label_url}
        badQuality subject text:{shipping_label_url} html:{shipping_label_url}
        moneySent subject text:{shipping_label_url} html:{shipping_label_url}
        pickupTimeRequest subject text:{shipping_label_url} html:{shipping_label_url}
        transactionCanceled subject text:{shipping_label_url} html:{shipping_label_url}
    """
    for default in defaults.strip( ).split("\n"):
        (name, subject, text, html) = default.strip( ).split( )
        if EmailMessage.query.filter_by(name=name).first( ):
            continue
        m = EmailMessage( )
        m.name = name
        m.subject = subject
        m.text = text
        m.html = html
        db.session.add(m)
    db.session.commit( )

    # Content
    from admin import ContentForm
    fields = " ".join(s for (n,s) in ContentForm.field_sets).split( )
    for f in fields:
        c = Content.query.filter_by(name=f).first( )
        if c:
            continue
        c = Content( )
        c.name = f
        c.content = '"{}"-placeholder'.format(f)
        db.session.add(c)
    db.session.commit( )


admin = admin.Admin(app, index_view=AdminIndexView( ))
admin.add_view(SettingsView(name="General", url="settings", category='Settings'))
admin.add_view(EmailMessageView(name="Email Messages", url="email_messages", category='Settings'))
admin.add_view(ContentView(name="Content", url="content", category='Settings'))
admin.add_view(UserAdmin(db.session, name="Users", url="users", category='Database'))
admin.add_view(EmailLogAdmin(db.session, url="email_log", category='Database'))
admin.add_view(TransactionAdmin(db.session, name="Transactions", url="transactions", category='Database'))
admin.add_view(DocsView(name="Documentation", url="documentation", category='Misc'))

