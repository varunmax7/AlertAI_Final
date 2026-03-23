"""
Vercel Serverless Entry Point
"""
import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import app
except Exception as e:
    # If main app fails to import, serve a debug page
    from flask import Flask
    app = Flask(__name__)
    error_msg = str(e)
    
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def catch_all(path):
        return f"""
        <html>
        <body style="font-family: monospace; padding: 40px; background: #1a1a1a; color: #ff6b6b;">
            <h1>⚠️ App Import Error</h1>
            <pre style="background: #2d2d2d; padding: 20px; border-radius: 8px; color: #ffd93d; overflow-x: auto;">
{error_msg}
            </pre>
            <p style="color: #888;">Python version: {sys.version}</p>
        </body>
        </html>
        """, 500
