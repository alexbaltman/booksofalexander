
from mws import mws # docs: https://github.com/czpython/python-amazon-mws
from app import app
from models import Settings

from pprint import pprint

DEFAULT_DIMENSIONS = dict(
    Height = 12,
    Length = 10.5,
    Width = 1.5,
    Weight = 2
)

amz = mws.Products(app.config["MWS_ACCESS_KEY"], app.config["MWS_SECRET_KEY"], app.config["MWS_MERCHANT_ID"])


def evaluate_books(isbn):
    formula = dict((x.name, x.value) for x in Settings.query.all( )) # XXX: Optimazation: save in mem cache
    f = lambda (name): int(formula["buy_formula_" + name])
    # Get book infos
    books = dict( )
    wont_buy = dict( )
    invalide_isbn = list( )
    for isbn in get_iter_chunks(isbn, 5): # The API has a limit of 5 IDs
        r = amz.get_matching_product_for_id(app.config["MWS_MARKETPLACE_ID"], "ISBN", isbn)
        r = r.parsed
        #pprint(r)
        if not isinstance(r, list):
            r = [r]
        for b in r:
            if 'Error' in b:
                invalide_isbn.append(b["Id"]["value"])
            else:
                if isinstance(b["Products"]["Product"], list):
                    # For some reason Amazon returns sometimes both, the non-Kindle and the Kindle version. We don't want the Kindle version
                    for x in b["Products"]["Product"]:
                        if x['AttributeSets']['ItemAttributes']['Binding']['value'] != "Kindle Edition":
                            b["Products"]["Product"] = x
                            break
                asin = b["Products"]["Product"]["Identifiers"]["MarketplaceASIN"]["ASIN"]["value"]
                title = b["Products"]["Product"]["AttributeSets"]["ItemAttributes"]["Title"]["value"]
                img = b["Products"]["Product"]["AttributeSets"]["ItemAttributes"]["SmallImage"]
                if "ItemDimensions" in b["Products"]["Product"]["AttributeSets"]["ItemAttributes"]:
                    dim = b["Products"]["Product"]["AttributeSets"]["ItemAttributes"]["ItemDimensions"]
                elif "PackageDimensions" in b["Products"]["Product"]["AttributeSets"]["ItemAttributes"]:
                    dim = b["Products"]["Product"]["AttributeSets"]["ItemAttributes"]["PackageDimensions"]
                else:
                    dim = dict( ) # we'll use the defaults data from DEFAULT_DIMENSIONS, see below 
                for x in "Height Length Width".split( ):
                    if not x in dim:
                        # for some reason some results don't have these data
                        dim[x] = dict(
                            Units = dict(value="inches"),
                            value = DEFAULT_DIMENSIONS[x]
                        )
                    assert dim[x]["Units"]["value"] == "inches"
                if not "Weight" in dim:
                    # same as above
                    dim["Weight"] = dict(
                        Units = dict(value="pounds"),
                        value = DEFAULT_DIMENSIONS["Weight"]
                    )
                assert dim["Weight"]["Units"]["value"] == "pounds"
                books[asin] = dict(
                    title = title,
                    img_url = img["URL"]["value"],
                    img_width = img["Width"]["value"],
                    img_hight = img["Height"]["value"],
                    item_height = float(dim["Height"]["value"]),
                    item_width = float(dim["Width"]["value"]),
                    item_length = float(dim["Length"]["value"]),
                    item_weight = float(dim["Weight"]["value"]) * 16 # pounds to ounces
                )

    # Get book price infos
    for asin in get_iter_chunks(books.keys( ), 20): # API limit of 20
        r = amz.get_lowest_offer_listings_for_asin(app.config["MWS_MARKETPLACE_ID"], asin, condition="Used")
        r = r.parsed
        if not isinstance(r, list):
            r = [r]

        # Evaluating the books
        for lol in r:
            asin = lol["ASIN"]["value"]
            lol = lol['Product']['LowestOfferListings'].get('LowestOfferListing', [])
            if len(lol) < f("number_of_used_offers"):
                quote = 0.0
            else:
                for i, l in enumerate(lol, 1):
                    rating = l['Qualifiers']['SellerPositiveFeedbackRating']['value']
                    if not rating in ("Just Launched", "Less than 70%"): # ignoring sellers without a rating and with a rating of less than 70%
                        rating = int(rating.strip("%").split("-").pop(0))
                        if (l['SellerFeedbackCount'] >= f("number_of_ratings")
                            and rating >= f("customer_satisfaction")):
                            price = float(l['Price']['LandedPrice']['Amount']['value'])
                            quote = price / 100 * 53
                            break
                    if i == f("seller_to_consider"):
                        # Use the lowest-priced seller
                        price = float(lol[0]['Price']['LandedPrice']['Amount']['value'])
                        quote = price / 100 * f("quoted_percantage")
                        break

            if quote < 5.0:
                quote = quote - 2.0
                if quote < 0.0:
                    quote = 0.0
            if quote == 0.0:
                wont_buy[asin] = books[asin]
                del books[asin]
            else:
                quote = "{0:.2f}".format(quote)
                books[asin].update(
                    quote = float(quote), 
                    #quote_str = quote,
                    quantity = 1
                )

    return (books, wont_buy, invalide_isbn)


def get_iter_chunks(iterable, chuck_size):
    while iterable:
        yield iterable[:chuck_size]
        del iterable[:chuck_size]


