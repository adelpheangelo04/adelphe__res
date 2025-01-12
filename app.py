from flask import Flask
from models import db
from functions import init_db
from routes import app_routes

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key_here'
db.init_app(app)

#with app.app_context():
    #init_db(app)

app.register_blueprint(app_routes)

if __name__ == '__main__':
    app.run(debug=True)ls