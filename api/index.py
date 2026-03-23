from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return '<h1>AlertAI is alive!</h1><p>Basic test passed.</p>'

@app.route('/<path:path>')
def catch_all(path):
    return f'<h1>Route: {path}</h1>'
