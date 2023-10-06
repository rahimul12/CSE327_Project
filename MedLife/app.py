import os
import pathlib

import requests
from flask import Flask, session, abort, redirect, request, render_template, url_for
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta

app = Flask("MedLife")
app.config["SQLALCHEMY_DATABASE_URI"] = 'mysql://root:@localhost/medlife'
db = SQLAlchemy(app)
app.secret_key = "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"

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_CLIENT_ID = "853888832125-llhj81iuaold01co7k1b24bb6qrs46r1.apps.googleusercontent.com"
client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_uri="http://127.0.0.1:5000/callback"
)

#db models
class User(db.Model):
    UserID = db.Column(db.Integer, primary_key=True)
    Username = db.Column(db.String(255), nullable=False)
    Email = db.Column(db.String(255), nullable=False)

class Product_info(db.Model):
    productID = db.Column(db.Integer, primary_key=True)
    Manufacturer = db.Column(db.String(47), nullable=True)
    BrandName = db.Column(db.String(38), nullable=True)
    GenericName = db.Column(db.String(393), nullable=True)
    Strength = db.Column(db.String(265), nullable=True)
    Description = db.Column(db.String(26), nullable=True)
    Price = db.Column(db.String(72), nullable=True)

class Cart(db.Model):
    __tablename__ = 'cart'

    CartID = db.Column(db.Integer, primary_key=True)
    UserID = db.Column(db.Integer, ForeignKey('user.UserID'), nullable=False) 
    ProductID = db.Column(db.Integer, ForeignKey('product_info.productID'), nullable=False)
    Quantity = db.Column(db.Integer, nullable=False)

    # Define the relationship with Product_info
    product = relationship('Product_info', backref='cart_items')

class History(db.Model):
    HistoryID = db.Column(db.Integer, primary_key=True)
    UserID = db.Column(db.Integer, db.ForeignKey('user.UserID'), nullable=False)
    ProductID = db.Column(db.Integer, db.ForeignKey('product_info.productID'), nullable=False)
    Quantity = db.Column(db.Integer, nullable=False)
    Timestamp = db.Column(db.TIMESTAMP, default=datetime.utcnow, nullable=False)

    # Define relationships
    user = db.relationship('User', backref=db.backref('history_entries', lazy=True))
    product = db.relationship('Product_info', backref=db.backref('history_entries', lazy=True))

# Methods

def login_is_required(function):
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return abort(401)  # Authorization required
        else:
            return function()

    return wrapper

#@app.routes

#@app.route("/User", methods=["GET", "POST"])
# @app.route("/User")
# def User():
#     if "google_id" in session:
#         name = session["name"]
#         email = session["email"]

#         entry = User(name=name, email=email)
#         db.session.add(entry)
#         db.session.commit()
#         return render_template('shop.html', name = name)

@app.route("/login")
def login():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    flow.fetch_token(authorization_response=request.url)

    if not session["state"] == request.args["state"]:
        abort(500)  # State does not match!

    credentials = flow.credentials
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)

    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID
    )

    session["google_id"] = id_info.get("sub")
    session["name"] = id_info.get("name")
    session["email"] = id_info.get("email") 

    first_name = session["name"].split()[0]
    session["first_name"] = first_name

    # Check if a user with a specific email exists
    email_exists = db.session.query(User).filter(User.Email == session["email"]).count() > 0

    if email_exists == 0:
        # Create a new user and add it to the database
        new_user = User(Username=session["name"], Email=session["email"])
        db.session.add(new_user)
        db.session.commit()

    return redirect("/protected_area")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/")
def index():
    session.clear()
    return render_template('home.html')

@app.route("/shop")
def shop():
    products = Product_info.query.all()
    if "google_id" in session:
        return render_template('shop.html', name = session["name"], products=products)
    else:
        session.clear()
        return render_template('shop.html', products=products)

@app.route('/view_product/<int:product_id>')
def view_product(product_id):
    product_detail = Product_info.query.get_or_404(product_id)
    return render_template('product_details.html', product=product_detail)

@app.route('/search_products', methods=['GET', 'POST'])
def search_products():
    search_query = request.form.get('search_query')

    products = Product_info.query.filter(Product_info.GenericName.like(f"%{search_query}%")).all()

    if "google_id" in session:
        return render_template('shop.html', name = session["name"], products=products)
    else:
        session.clear()
        return render_template('shop.html', products=products)


@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if "google_id" in session:
        user = User.query.filter_by(Email=session["email"]).first()
        user_id = user.UserID
        quantity = int(request.form['quantity'])

        new_cart_item = Cart(ProductID=product_id, Quantity=quantity, UserID=user_id)
        db.session.add(new_cart_item)
        db.session.commit()

        # Retrieve the redirect URL from the request
        redirect_url = request.args.get('redirect_url', '/shop')

        return redirect(redirect_url)
    else:
        return redirect(url_for('login'))

@app.route('/cart')
def cart():
    if "google_id" in session:
        user = User.query.filter_by(Email=session["email"]).first()
        user_id = user.UserID
        cart_items = Cart.query.filter_by(UserID=user_id).all()

        total_price = 0

        for item in cart_items:
            item_price = float(item.product.Price)  # Convert to float
            item_quantity = float(item.Quantity)   # Convert to float
            total_price += item_price * item_quantity
            
        formatted_price = "{:.2f}".format(total_price)

        return render_template('cart.html', name = session["name"], cart_items=cart_items, total_price=formatted_price)
    else:
        return render_template('cart.html')
    
@app.route('/remove_from_cart/<int:cart_id>')
def remove_from_cart(cart_id):
    if "google_id" in session:
        cart_item = Cart.query.get_or_404(cart_id)
        db.session.delete(cart_item)
        db.session.commit()
        return redirect(url_for('cart'))
    else:
        return redirect(url_for('login'))

@app.route('/buy_all')
def buy_all():
    if "google_id" in session:
        user = User.query.filter_by(Email=session["email"]).first()
        user_id = user.UserID
        cart_items = Cart.query.filter_by(UserID=user_id).all()

        for item in cart_items:
            new_history_item = History(
                UserID=user_id,
                ProductID=item.ProductID,
                Quantity=item.Quantity,
                Timestamp=datetime.utcnow() + timedelta(hours=6)
            )
            db.session.add(new_history_item)
            db.session.delete(item)  # Remove item from cart

        db.session.commit()

        return redirect(url_for('cart'))

    else:
        return redirect(url_for('login'))

@app.route('/history')
def history():
    if "google_id" in session:
        user = User.query.filter_by(Email=session["email"]).first()
        user_id = user.UserID
        history_items = History.query.filter_by(UserID=user_id).all()

        total_price = 0

        for item in history_items:
            item_price = float(item.product.Price)  # Convert to float
            item_quantity = float(item.Quantity)   # Convert to float
            total_price += item_price * item_quantity
            
        formatted_price = "{:.2f}".format(total_price)
        
        return render_template('history.html', name = session["name"], history_items=history_items, total_price=formatted_price)
    else:
        return render_template('history.html')

@app.route('/clear_history')
def clear_history():
    if "google_id" in session:
        user = User.query.filter_by(Email=session["email"]).first()
        user_id = user.UserID

        History.query.filter_by(UserID=user_id).delete()
        db.session.commit()

        return redirect(url_for('history'))
    else:
        return redirect(url_for('login'))



@app.route("/protected_area")
@login_is_required
def protected_area():
    return render_template('home.html', name = session["name"]) 


if __name__ == "__main__":
    app.run(debug=True)