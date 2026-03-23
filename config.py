import os

class Config:
    # Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY', 'emergency-system-secret-key-2024')
    
    # Check if running on Vercel
    IS_VERCEL = os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_URL') is not None
    
    if IS_VERCEL:
        SESSION_TYPE = 'null'
        DATABASE_PATH = '/tmp/emergency.db'
        SOCKETIO_ASYNC_MODE = None  # Disable threading for Vercel lambdas
    else:
        SESSION_TYPE = 'filesystem'
        DATABASE_PATH = 'database/emergency.db'
        SOCKETIO_ASYNC_MODE = 'threading'
    
    # Database config
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Socket.IO config - fallback for when not using IS_VERCEL logic
    # SOCKETIO_ASYNC_MODE = 'threading'
    
    # PWA config
    PWA_NAME = 'Emergency Response System'
    PWA_THEME_COLOR = '#dc3545'
    
    # AI Classification config
    SEVERITY_RULES = {
        'fire': 'critical',
        'medical': 'high',
        'crime': 'high',
        'accident': 'medium',
        'natural': 'high',
        'other': 'low'
    }
    
    # Response time config
    RESPONSE_TIME_CRITICAL = 5
    RESPONSE_TIME_HIGH = 10
    RESPONSE_TIME_MEDIUM = 30
    RESPONSE_TIME_LOW = 60
    
    # Community helper radius
    COMMUNITY_HELPER_RADIUS = 5
    
    # Leaderboard points
    POINTS_PER_HELP = 10
    POINTS_PER_INCIDENT = 20
    POINTS_FAST_RESPONSE = 15
    
    # Debug mode
    DEBUG = os.environ.get('FLASK_DEBUG', 'False') == 'True'

# Use this config
config = Config