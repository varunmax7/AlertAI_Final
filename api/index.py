import sys
import os
import traceback

# Attempt to import the real app with full error details
try:
    # Add parent directory to Python path
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    from app import app
    
except Exception as e:
    # If real app fails, show the EXACT error on screen
    from flask import Flask
    app = Flask(__name__)
    
    error_details = traceback.format_exc()
    
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def error_page(path):
        return f"""<html>
<body style="font-family:monospace; padding:40px; background:#111; color:#fff;">
<h1 style="color:#ff4444;">Import Error Caught!</h1>
<h3>Python: {sys.version}</h3>
<h3>Working Dir: {os.getcwd()}</h3>
<h3>Parent Dir: {parent_dir}</h3>
<h3>Files in parent:</h3>
<pre style="color:#88ff88;">{os.listdir(parent_dir)}</pre>
<h3>Full Error:</h3>
<pre style="background:#222; padding:20px; color:#ffaa00; white-space:pre-wrap;">{error_details}</pre>
</body></html>""", 500
