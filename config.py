import os

class Config:
    # Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY', 'emergency-system-secret-key-2024')
    
    # Check if running on Vercel
    IS_VERCEL = os.environ.get('VERCEL') == '1'
    
    if IS_VERCEL:
        SESSION_TYPE = 'null'  # Use standard cookie sessions on Vercel
        DATABASE_PATH = '/tmp/emergency.db'
    else:
        SESSION_TYPE = 'filesystem'
        DATABASE_PATH = 'database/emergency.db'
    
    # Database config
    # Allow override via ENV for future professional database connection
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Socket.IO config
    SOCKETIO_ASYNC_MODE = 'threading'
    
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
    RESPONSE_TIME_CRITICAL = 5  # minutes
    RESPONSE_TIME_HIGH = 10     # minutes
    RESPONSE_TIME_MEDIUM = 30   # minutes
    RESPONSE_TIME_LOW = 60      # minutes
    
    # Community helper radius (in km)
    COMMUNITY_HELPER_RADIUS = 5
    
    # Leaderboard points
    POINTS_PER_HELP = 10
    POINTS_PER_INCIDENT = 20
    POINTS_FAST_RESPONSE = 15
    
    # Debug mode
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'

# Use this config
config = Config