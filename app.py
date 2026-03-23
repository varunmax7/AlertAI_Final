"""
AI-Powered Emergency Response & Incident Management System
Main Application File
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_socketio import SocketIO, emit
from flask_session import Session
import sqlite3
import hashlib
import json
import os
from datetime import datetime
from functools import wraps
import logging
import math

from app_config import config as app_cfg

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = app_cfg.SECRET_KEY
app.config['SESSION_TYPE'] = app_cfg.SESSION_TYPE
app.debug = app_cfg.DEBUG

# Initialize extensions
# Wrap in try-except to prevent crash on environments where Session extension is unsupported
try:
    Session(app)
except Exception as e:
    logger.warning(f"Session initialization failed: {e}")

try:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode=app_cfg.SOCKETIO_ASYNC_MODE)
except Exception as e:
    logger.warning(f"SocketIO initialization failed: {e}")
    # Create a mock socketio object to prevent errors in routes
    class MockSocketIO:
        def emit(self, *args, **kwargs): pass
        def on(self, *args, **kwargs): return lambda f: f
    socketio = MockSocketIO()

# Database connection
def get_db_connection():
    """Create and return a database connection"""
    conn = sqlite3.connect(app_cfg.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Password hashing
def hash_password(password):
    """Hash password using PBKDF2 with SHA256"""
    salt = b'emergency_system_salt_2024'
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()

# Authentication decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if session.get('user_type') != role:
                flash('Access denied. Insufficient permissions.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Helper function to calculate distance between coordinates (Haversine formula)
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in kilometers"""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

# AI Incident Classification
def classify_incident(emergency_type, description=""):
    """
    AI-based rule engine for incident classification
    Returns severity level based on emergency type and description analysis
    """
    # Get base severity from rules
    severity = app_cfg.SEVERITY_RULES.get(emergency_type.lower(), 'medium')
    
    # Keyword analysis for severity adjustment
    description_lower = description.lower()
    
    # Critical keywords
    critical_keywords = [
        'urgent', 'critical', 'dying', 'fire', 'explosion', 'gun', 'shoot',
        'bomb', 'collapse', 'trapped', 'unconscious', 'not breathing'
    ]
    
    # High severity keywords
    high_keywords = [
        'serious', 'severe', 'bleeding', 'robbery', 'attack', 'assault',
        'accident', 'injured', 'pain', 'emergency', 'help'
    ]
    
    # Check for critical keywords
    for keyword in critical_keywords:
        if keyword in description_lower:
            severity = 'critical'
            break
    
    # Check for high keywords (only if not already critical)
    if severity != 'critical':
        for keyword in high_keywords:
            if keyword in description_lower:
                severity = 'high'
                break
    
    # Adjust based on emergency type
    if emergency_type.lower() == 'medical':
        medical_critical = ['heart', 'stroke', 'choking', 'seizure']
        for keyword in medical_critical:
            if keyword in description_lower:
                severity = 'critical'
                break
    
    return severity

# Initialize Database
def init_db():
    """Initialize database with schema"""
    db_path = app_cfg.DATABASE_PATH
    db_dir = os.path.dirname(db_path)
    
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create database directory {db_dir}: {e}")

    if not os.path.exists(app_cfg.DATABASE_PATH):
        logger.info(f"Creating new database at {app_cfg.DATABASE_PATH}...")
        conn = get_db_connection()
        
        # Create tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                gov_id TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                verification_status TEXT DEFAULT 'pending',
                latitude REAL,
                longitude REAL,
                is_sharing_location BOOLEAN DEFAULT 0,
                skills TEXT DEFAULT '',
                help_count INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS responders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                password TEXT NOT NULL,
                availability BOOLEAN DEFAULT 1,
                latitude REAL,
                longitude REAL,
                vehicle_number TEXT,
                contact_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                incidents_handled INTEGER DEFAULT 0,
                response_score INTEGER DEFAULT 0
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                emergency_type TEXT NOT NULL,
                description TEXT,
                severity TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'reported',
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                people_affected TEXT DEFAULT '',
                immediate_danger TEXT DEFAULT '',
                can_assist TEXT DEFAULT 'no',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS incident_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                performed_by TEXT NOT NULL,
                performed_role TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (incident_id) REFERENCES incidents (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                assignee_id INTEGER NOT NULL,
                assignee_type TEXT NOT NULL,
                status TEXT DEFAULT 'assigned',
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_at TIMESTAMP,
                arrived_at TIMESTAMP,
                completed_at TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (incident_id) REFERENCES incidents (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS community_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT DEFAULT 'requested',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_at TIMESTAMP,
                arrived_at TIMESTAMP,
                completed_at TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (incident_id) REFERENCES incidents (id),
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(incident_id, user_id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_location_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_type TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                accuracy REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_type TEXT NOT NULL,
                badge_type TEXT NOT NULL,
                badge_name TEXT NOT NULL,
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_type TEXT NOT NULL,
                rank INTEGER,
                points INTEGER DEFAULT 0,
                monthly_points INTEGER DEFAULT 0,
                badges TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                notification_type TEXT,
                is_read BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # Hash default admin password
        default_password = hash_password('admin123')
        conn.execute("INSERT OR IGNORE INTO admin_users (username, password) VALUES ('admin', ?)", 
                    (default_password,))
        
        # Insert sample responders for testing
        sample_responders = [
            ('John Ambulance', 'ambulance1@test.com', 'ambulance', hash_password('test123'), 'AMB-001', '+1234567890'),
            ('Police Unit 1', 'police1@test.com', 'police', hash_password('test123'), 'POL-001', '+1234567891'),
            ('Fire Truck 1', 'fire1@test.com', 'fire', hash_password('test123'), 'FIR-001', '+1234567892')
        ]
        
        for responder in sample_responders:
            conn.execute('''
                INSERT OR IGNORE INTO responders (name, email, role, password, vehicle_number, contact_number)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', responder)
        
        # Insert some sample verified users for community assistance
        sample_users = [
            ('John Doe', 'john@example.com', '+1234567893', 'ID123456', hash_password('test123'), 'verified', 28.6139, 77.2090, 'medical,first-aid'),
            ('Jane Smith', 'jane@example.com', '+1234567894', 'ID123457', hash_password('test123'), 'verified', 28.6145, 77.2095, 'rescue'),
            ('Bob Wilson', 'bob@example.com', '+1234567895', 'ID123458', hash_password('test123'), 'verified', 28.6135, 77.2085, 'fire,rescue'),
            ('Alice Brown', 'alice@example.com', '+1234567896', 'ID123459', hash_password('test123'), 'verified', 28.6150, 77.2100, 'first-aid'),
        ]
        
        for user in sample_users:
            conn.execute('''
                INSERT OR IGNORE INTO users (name, email, phone, gov_id, password, verification_status, latitude, longitude, skills)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', user)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully!")
    else:
        logger.info("Database already exists.")

# Lazy initialization flag
_db_initialized = False

@app.before_request
def ensure_db_initialized():
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception as e:
            logger.error(f"Lazy init_db failed: {e}")

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Home page redirects based on login status"""
    if 'user_id' in session:
        user_type = session.get('user_type')
        if user_type == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user_type == 'responder':
            return redirect(url_for('responder_dashboard'))
        else:
            return redirect(url_for('citizen_dashboard'))
    
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for all user types"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        user_type = request.form.get('user_type', 'citizen')
        
        if not email or not password:
            flash('Please fill in all fields', 'danger')
            return render_template('login.html')
        
        conn = get_db_connection()
        user = None
        
        try:
            if user_type == 'citizen':
                user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            elif user_type == 'responder':
                user = conn.execute('SELECT * FROM responders WHERE email = ?', (email,)).fetchone()
            elif user_type == 'admin':
                user = conn.execute('SELECT * FROM admin_users WHERE username = ?', (email,)).fetchone()
            else:
                flash('Invalid user type', 'danger')
                conn.close()
                return render_template('login.html')
            
            if user:
                # Verify password
                hashed_input = hash_password(password)
                
                if user_type == 'admin':
                    # For admin, check hashed password
                    if user['password'] == hashed_input:
                        session['user_id'] = user['id']
                        session['user_type'] = 'admin'
                        session['username'] = user['username']
                        flash('Login successful!', 'success')
                        conn.close()
                        return redirect(url_for('admin_dashboard'))
                else:
                    if user['password'] == hashed_input:
                        # Check if citizen is verified
                        if user_type == 'citizen' and user['verification_status'] != 'verified':
                            flash('Your account is pending verification by admin', 'warning')
                            conn.close()
                            return render_template('login.html')
                        
                        session['user_id'] = user['id']
                        session['user_type'] = user_type
                        session['username'] = user['name']
                        
                        flash('Login successful!', 'success')
                        conn.close()
                        
                        # Redirect to appropriate dashboard
                        if user_type == 'citizen':
                            return redirect(url_for('citizen_dashboard'))
                        elif user_type == 'responder':
                            return redirect(url_for('responder_dashboard'))
                        else:
                            return redirect(url_for('index'))
            
            flash('Invalid email or password', 'danger')
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash('An error occurred during login', 'danger')
        
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/register/citizen', methods=['GET', 'POST'])
def citizen_register():
    """Citizen registration page"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        gov_id = request.form.get('gov_id', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validation
        errors = []
        if not all([name, email, phone, gov_id, password, confirm_password]):
            errors.append('All fields are required')
        
        if password != confirm_password:
            errors.append('Passwords do not match')
        
        if len(password) < 6:
            errors.append('Password must be at least 6 characters')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register_citizen.html')
        
        conn = get_db_connection()
        
        try:
            # Check if email already exists
            existing_email = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
            if existing_email:
                flash('Email already registered', 'danger')
                conn.close()
                return render_template('register_citizen.html')
            
            # Check if gov_id already exists
            existing_gov = conn.execute('SELECT id FROM users WHERE gov_id = ?', (gov_id,)).fetchone()
            if existing_gov:
                flash('Government ID already registered', 'danger')
                conn.close()
                return render_template('register_citizen.html')
            
            # Create user
            hashed_password = hash_password(password)
            conn.execute('''
                INSERT INTO users (name, email, phone, gov_id, password, verification_status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, email, phone, gov_id, hashed_password, 'pending'))
            
            conn.commit()
            flash('Registration successful! Your account will be verified by admin within 24 hours.', 'success')
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            flash('An error occurred during registration', 'danger')
        
        finally:
            conn.close()
    
    return render_template('register_citizen.html')

# ==================== CITIZEN ROUTES ====================

@app.route('/dashboard/citizen')
@role_required('citizen')
def citizen_dashboard():
    """Citizen dashboard"""
    conn = get_db_connection()
    user = None
    incidents = []
    pending_assignments = []
    active_assignments = []
    leaderboard_pos = None
    
    try:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        if not user:
            session.clear()
            flash('Session expired. Please login again.', 'warning')
            return redirect(url_for('login'))
        
        # Get recent incidents from this user
        try:
            incidents = conn.execute('''
                SELECT * FROM incidents 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT 5
            ''', (session['user_id'],)).fetchall() or []
        except Exception as e:
            logger.debug(f"Could not fetch incidents: {e}")
            incidents = []
        
        # Try to get community assignments (if table exists)
        try:
            pending_assignments = conn.execute('''
                SELECT * FROM community_assignments 
                WHERE user_id = ? AND status = 'requested'
                ORDER BY created_at DESC
                LIMIT 5
            ''', (session['user_id'],)).fetchall() or []
        except Exception as e:
            logger.debug(f"Could not fetch pending assignments: {e}")
            pending_assignments = []
        
        try:
            active_assignments = conn.execute('''
                SELECT * FROM community_assignments 
                WHERE user_id = ? AND status IN ('accepted', 'arrived')
                ORDER BY created_at DESC
                LIMIT 5
            ''', (session['user_id'],)).fetchall() or []
        except Exception as e:
            logger.debug(f"Could not fetch active assignments: {e}")
            active_assignments = []
        
        # Get leaderboard position
        try:
            user_points = user['points'] if user['points'] else 0
            user_help = user['help_count'] if user['help_count'] else 0
            
            if user['verification_status'] == 'verified':
                higher_count_row = conn.execute('''
                    SELECT COUNT(*) as cnt FROM users
                    WHERE verification_status = 'verified'
                    AND (points > ? OR (points = ? AND help_count > ?))
                ''', (user_points, user_points, user_help)).fetchone()

                higher_count = higher_count_row['cnt'] if higher_count_row else 0
                rank = higher_count + 1
                leaderboard_pos = {'rank': rank, 'points': user_points, 'help_count': user_help}
        except Exception as e:
            logger.debug(f"Leaderboard calculation skipped: {e}")
            leaderboard_pos = None
        
    except Exception as e:
        logger.error(f"Citizen Dashboard error: {e}")
        session.clear()
        flash('Error loading dashboard. Please login again.', 'danger')
        return redirect(url_for('login'))
    
    finally:
        conn.close()
    
    return render_template('citizen_dashboard.html', 
                         user=user, 
                         incidents=incidents,
                         pending_assignments=pending_assignments,
                         active_assignments=active_assignments,
                         leaderboard=leaderboard_pos)

@app.route('/emergency/report', methods=['GET', 'POST'])
@role_required('citizen')
def report_emergency():
    """Emergency reporting page"""
    if request.method == 'POST':
        emergency_type = request.form.get('emergency_type', '').strip()
        description = request.form.get('description', '').strip()
        latitude = request.form.get('latitude', '')
        longitude = request.form.get('longitude', '')
        people_affected = request.form.get('people_affected', '')
        immediate_danger = request.form.get('immediate_danger', '')
        can_assist = request.form.get('can_assist', 'no')
        
        # Validation
        if not emergency_type:
            return jsonify({'success': False, 'error': 'Emergency type is required'}), 400
        
        if not latitude or not longitude:
            # For demo, use default location
            latitude, longitude = '28.6139', '77.2090'
        
        try:
            lat = float(latitude)
            lng = float(longitude)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid location coordinates'}), 400
        
        conn = get_db_connection()
        
        try:
            # AI classification
            severity = classify_incident(emergency_type, description)
            
            # Create incident
            cursor = conn.execute('''
                INSERT INTO incidents (user_id, emergency_type, description, severity, status, 
                                      latitude, longitude, people_affected, immediate_danger, can_assist)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], emergency_type, description, severity, 'reported', 
                  lat, lng, people_affected, immediate_danger, can_assist))
            
            incident_id = cursor.lastrowid
            
            # Log the action
            conn.execute('''
                INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
                VALUES (?, ?, ?, ?)
            ''', (incident_id, 'incident_reported', str(session['user_id']), 'citizen'))
            
            conn.commit()
            
            # Notify via Socket.IO
            socketio.emit('new_incident', {
                'id': incident_id,
                'type': emergency_type,
                'severity': severity,
                'location': {'lat': lat, 'lng': lng},
                'timestamp': datetime.now().isoformat()
            })
            
            return jsonify({
                'success': True, 
                'incident_id': incident_id,
                'message': 'Emergency reported successfully! Help is on the way.'
            })
            
        except Exception as e:
            logger.error(f"Report error: {e}")
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        
        finally:
            conn.close()
    
    return render_template('report_emergency.html')

# ==================== RESPONDER ROUTES ====================

@app.route('/dashboard/responder')
@role_required('responder')
def responder_dashboard():
    """Responder dashboard"""
    conn = get_db_connection()
    responder = None
    assigned_incidents = []
    active_incidents = []
    
    try:
        responder = conn.execute('SELECT * FROM responders WHERE id = ?', (session['user_id'],)).fetchone()
        
        if not responder:
            session.clear()
            flash('Session expired. Please login again.', 'warning')
            return redirect(url_for('login'))
        
        # Get assigned incidents
        try:
            assigned_incidents = conn.execute('''
                SELECT i.*, u.name as user_name, u.phone as user_phone
                FROM incidents i
                JOIN users u ON i.user_id = u.id
                JOIN assignments a ON a.incident_id = i.id
                WHERE a.assignee_id = ? AND a.assignee_type = 'responder'
                AND a.status != 'completed'
                ORDER BY i.created_at DESC
                LIMIT 10
            ''', (session['user_id'],)).fetchall() or []
        except Exception as e:
            logger.debug(f"Could not fetch assigned incidents: {e}")
            assigned_incidents = []
        
        # Get active incidents nearby using Python-based distance calculation
        try:
            # Default location if responder location is not set
            resp_lat = responder['latitude'] if responder['latitude'] else 28.6139
            resp_lon = responder['longitude'] if responder['longitude'] else 77.2090
            
            # Get all active incidents
            incidents_result = conn.execute('''
                SELECT i.*, u.name as user_name
                FROM incidents i
                JOIN users u ON i.user_id = u.id
                WHERE i.status IN ('reported', 'approved', 'dispatched')
                ORDER BY i.created_at DESC
                LIMIT 20
            ''').fetchall() or []
            
            # Calculate distances using Python (Haversine formula)
            incidents_with_distance = []
            for incident in incidents_result:
                distance = calculate_distance(
                    resp_lat, resp_lon,
                    incident['latitude'], incident['longitude']
                )
                incident_dict = dict(incident)
                incident_dict['distance'] = round(distance, 2)
                incidents_with_distance.append(incident_dict)
            
            # Sort by distance and take top 10
            active_incidents = sorted(incidents_with_distance, key=lambda x: x['distance'])[:10]
        except Exception as e:
            logger.debug(f"Could not fetch active incidents: {e}")
            active_incidents = []
        
    except Exception as e:
        logger.error(f"Responder dashboard error: {e}")
        session.clear()
        flash('Error loading dashboard. Please login again.', 'danger')
        return redirect(url_for('login'))
    
    finally:
        conn.close()
    
    return render_template('responder_dashboard.html',
                         responder=responder,
                         assigned_incidents=assigned_incidents,
                         active_incidents=active_incidents)

# ==================== ADMIN ROUTES ====================

@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    """Admin dashboard"""
    conn = get_db_connection()
    
    try:
        # Get stats
        total_incidents = conn.execute('SELECT COUNT(*) FROM incidents').fetchone()[0]
        active_incidents = conn.execute("SELECT COUNT(*) FROM incidents WHERE status NOT IN ('resolved', 'closed')").fetchone()[0]
        total_users = conn.execute("SELECT COUNT(*) FROM users WHERE verification_status = 'verified'").fetchone()[0]
        total_pending = conn.execute("SELECT COUNT(*) FROM users WHERE verification_status = 'pending'").fetchone()[0]
        available_responders = conn.execute("SELECT COUNT(*) FROM responders WHERE availability = 1").fetchone()[0]
        
        # Get list of available responders for assignment
        responders_list = conn.execute("SELECT id, name, role FROM responders WHERE availability = 1").fetchall()
        
        # Get recent incidents
        recent_incidents = conn.execute('''
            SELECT i.*, u.name as user_name
            FROM incidents i
            JOIN users u ON i.user_id = u.id
            ORDER BY i.created_at DESC 
            LIMIT 10
        ''').fetchall()
        
        # Get pending verifications
        pending_users = conn.execute('''
            SELECT * FROM users 
            WHERE verification_status = 'pending'
            ORDER BY created_at DESC 
            LIMIT 10
        ''').fetchall()
        
        # Get counts for sidebar
        active_incidents_count = active_incidents
        pending_users_count = total_pending
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        flash('Error loading dashboard', 'danger')
        return redirect(url_for('index'))
    
    finally:
        conn.close()
    
    return render_template('admin_dashboard.html',
                         total_incidents=total_incidents,
                         active_incidents=active_incidents,
                         total_users=total_users,
                         total_pending=total_pending,
                         available_responders=available_responders,
                         recent_incidents=recent_incidents,
                         pending_users=pending_users,
                         responders_list=responders_list,
                         active_incidents_count=active_incidents_count,
                         pending_users_count=pending_users_count)

@app.route('/admin/verify_user/<int:user_id>')
@role_required('admin')
def verify_user(user_id):
    """Verify a user account"""
    conn = get_db_connection()
    
    try:
        conn.execute('UPDATE users SET verification_status = ? WHERE id = ?', 
                    ('verified', user_id))
        conn.commit()
        flash('User verified successfully!', 'success')
    except Exception as e:
        logger.error(f"Verify user error: {e}")
        flash('Error verifying user', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/incidents')
@role_required('admin')
def admin_incidents():
    """Admin incidents management"""
    conn = get_db_connection()
    
    try:
        incidents = conn.execute('''
            SELECT i.*, u.name as user_name, u.phone as user_phone
            FROM incidents i
            JOIN users u ON i.user_id = u.id
            ORDER BY i.created_at DESC
        ''').fetchall()
        
        # Get counts for sidebar
        active_incidents_count = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE status NOT IN ('resolved', 'closed')"
        ).fetchone()[0]
        
        pending_users_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE verification_status = 'pending'"
        ).fetchone()[0]
        
    except Exception as e:
        logger.error(f"Incidents error: {e}")
        flash('Error loading incidents', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    finally:
        conn.close()
    
    return render_template('admin_incidents.html', 
                         incidents=incidents,
                         active_incidents_count=active_incidents_count,
                         pending_users_count=pending_users_count)

@app.route('/admin/responders')
@role_required('admin')
def admin_responders():
    """Admin responders management"""
    conn = get_db_connection()
    
    try:
        responders = conn.execute('SELECT * FROM responders ORDER BY created_at DESC').fetchall()
        
        # Get counts for sidebar
        active_incidents_count = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE status NOT IN ('resolved', 'closed')"
        ).fetchone()[0]
        
        pending_users_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE verification_status = 'pending'"
        ).fetchone()[0]
        
    except Exception as e:
        logger.error(f"Responders error: {e}")
        flash('Error loading responders', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    finally:
        conn.close()
    
    return render_template('admin_responders.html', 
                         responders=responders,
                         active_incidents_count=active_incidents_count,
                         pending_users_count=pending_users_count)

@app.route('/admin/incident/<int:incident_id>')
@role_required('admin')
def incident_details(incident_id):
    """Detailed incident view"""
    conn = get_db_connection()
    
    try:
        incident = conn.execute('''
            SELECT i.*, u.name as user_name, u.phone as user_phone, u.email as user_email
            FROM incidents i
            LEFT JOIN users u ON i.user_id = u.id
            WHERE i.id = ?
        ''', (incident_id,)).fetchone()
        
        if not incident:
            flash('Incident not found', 'danger')
            return redirect(url_for('admin_incidents'))
        
        # Get assignments
        assignments = conn.execute('''
            SELECT a.*, 
                   CASE 
                       WHEN a.assignee_type = 'responder' THEN r.name
                       WHEN a.assignee_type = 'user' THEN u.name
                   END as assignee_name,
                   CASE 
                       WHEN a.assignee_type = 'responder' THEN r.role
                       WHEN a.assignee_type = 'user' THEN 'community_helper'
                   END as assignee_role
            FROM assignments a
            LEFT JOIN responders r ON a.assignee_type = 'responder' AND a.assignee_id = r.id
            LEFT JOIN users u ON a.assignee_type = 'user' AND a.assignee_id = u.id
            WHERE a.incident_id = ?
        ''', (incident_id,)).fetchall()
        
        # Get community assignments
        community_assignments = conn.execute('''
            SELECT ca.*, u.name as user_name, u.phone as user_phone
            FROM community_assignments ca
            JOIN users u ON ca.user_id = u.id
            WHERE ca.incident_id = ?
            ORDER BY ca.requested_at DESC
        ''', (incident_id,)).fetchall()
        
        # Get logs
        logs = conn.execute('''
            SELECT * FROM incident_logs 
            WHERE incident_id = ? 
            ORDER BY timestamp DESC
        ''', (incident_id,)).fetchall()
        
        # Get available responders for assignment
        available_responders = conn.execute('''
            SELECT * FROM responders 
            WHERE availability = 1
            ORDER BY role, name
        ''').fetchall()
        
        # Get nearby users for community assignment
        nearby_users = conn.execute('''
            SELECT u.*,
                   ROUND(111.045 * DEGREES(ACOS(
                       COS(RADIANS(?)) * COS(RADIANS(u.latitude)) *
                       COS(RADIANS(?) - RADIANS(u.longitude)) +
                       SIN(RADIANS(?)) * SIN(RADIANS(u.latitude))
                   )), 2) as distance
            FROM users u
            WHERE u.verification_status = 'verified'
            AND u.latitude IS NOT NULL
            AND u.longitude IS NOT NULL
            AND u.id != ?
            HAVING distance <= 5
            ORDER BY distance
            LIMIT 20
        ''', (incident['latitude'], incident['longitude'], 
              incident['latitude'], incident['user_id'])).fetchall()
        
    except Exception as e:
        logger.error(f"Incident details error: {e}")
        flash('Error loading incident details', 'danger')
        return redirect(url_for('admin_incidents'))
    
    finally:
        conn.close()
    
    return render_template('incident_details.html',
                         incident=incident,
                         assignments=assignments,
                         community_assignments=community_assignments,
                         logs=logs,
                         available_responders=available_responders,
                         nearby_users=nearby_users)

# ==================== COMMUNITY ASSISTANCE ROUTES ====================

@app.route('/admin/incident/<int:incident_id>/assign_community')
@role_required('admin')
def assign_community_helpers(incident_id):
    """Page to assign community helpers to an incident"""
    conn = get_db_connection()
    
    try:
        # Get incident details
        incident = conn.execute('''
            SELECT i.*, u.name as user_name
            FROM incidents i
            LEFT JOIN users u ON i.user_id = u.id
            WHERE i.id = ?
        ''', (incident_id,)).fetchone()
        
        if not incident:
            flash('Incident not found', 'danger')
            return redirect(url_for('admin_incidents'))
        
        # Get nearby verified users (within 5km radius)
        radius = 5  # km
        nearby_users = conn.execute('''
            SELECT u.*,
                   ROUND(111.045 * DEGREES(ACOS(
                       COS(RADIANS(?)) * COS(RADIANS(u.latitude)) *
                       COS(RADIANS(?) - RADIANS(u.longitude)) +
                       SIN(RADIANS(?)) * SIN(RADIANS(u.latitude))
                   )), 2) as distance
            FROM users u
            WHERE u.verification_status = 'verified'
            AND u.latitude IS NOT NULL
            AND u.longitude IS NOT NULL
            AND u.id != ?
            HAVING distance <= ?
            ORDER BY distance
            LIMIT 20
        ''', (incident['latitude'], incident['longitude'], 
              incident['latitude'], incident['user_id'], radius)).fetchall()
        
        # Check if already has community assignments
        existing_assignments = conn.execute('''
            SELECT COUNT(*) FROM community_assignments 
            WHERE incident_id = ? AND status != 'declined'
        ''', (incident_id,)).fetchone()[0]
        
        if existing_assignments > 0:
            flash('Community helpers already assigned to this incident', 'info')
            return redirect(url_for('incident_details', incident_id=incident_id))
        
    except Exception as e:
        logger.error(f"Community assignment error: {e}")
        flash('Error loading assignment page', 'danger')
        return redirect(url_for('incident_details', incident_id=incident_id))
    
    finally:
        conn.close()
    
    return render_template('community_assign.html',
                         incident=incident,
                         nearby_users=nearby_users,
                         radius=radius)

# ==================== API ROUTES ====================

@app.route('/api/incidents/<int:incident_id>')
@login_required
def get_incident(incident_id):
    """Get incident details"""
    conn = get_db_connection()
    
    try:
        incident = conn.execute('''
            SELECT i.*, u.name as user_name, u.phone as user_phone
            FROM incidents i
            JOIN users u ON i.user_id = u.id
            WHERE i.id = ?
        ''', (incident_id,)).fetchone()
        
        if not incident:
            return jsonify({'error': 'Incident not found'}), 404
        
        # Check permissions
        user_type = session.get('user_type')
        user_id = session.get('user_id')
        
        if user_type == 'citizen' and incident['user_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get assignments
        assignments = conn.execute('''
            SELECT a.*, 
                   CASE 
                       WHEN a.assignee_type = 'responder' THEN r.name
                       WHEN a.assignee_type = 'user' THEN u.name
                   END as assignee_name,
                   CASE 
                       WHEN a.assignee_type = 'responder' THEN r.role
                       WHEN a.assignee_type = 'user' THEN 'community_helper'
                   END as assignee_role
            FROM assignments a
            LEFT JOIN responders r ON a.assignee_type = 'responder' AND a.assignee_id = r.id
            LEFT JOIN users u ON a.assignee_type = 'user' AND a.assignee_id = u.id
            WHERE a.incident_id = ?
        ''', (incident_id,)).fetchall()
        
        # Get community assignments
        community_assignments = conn.execute('''
            SELECT ca.*, u.name as user_name
            FROM community_assignments ca
            JOIN users u ON ca.user_id = u.id
            WHERE ca.incident_id = ?
        ''', (incident_id,)).fetchall()
        
        incident_dict = dict(incident)
        incident_dict['assignments'] = [dict(a) for a in assignments]
        incident_dict['community_assignments'] = [dict(ca) for ca in community_assignments]
        
        return jsonify(incident_dict)
        
    except Exception as e:
        logger.error(f"Get incident error: {e}")
        return jsonify({'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/nearby_responders')
@login_required
def get_nearby_responders():
    """Get nearby available responders"""
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 10, type=float)  # km
    
    if not lat or not lng:
        lat, lng = 28.6139, 77.2090  # Default to New Delhi
    
    conn = get_db_connection()
    
    try:
        # Get responders with distance calculation
        responders = conn.execute('''
            SELECT r.*,
                   ROUND(111.045 * DEGREES(ACOS(
                       COS(RADIANS(?)) * COS(RADIANS(r.latitude)) *
                       COS(RADIANS(?) - RADIANS(r.longitude)) +
                       SIN(RADIANS(?)) * SIN(RADIANS(r.latitude))
                   )), 2) as distance
            FROM responders r
            WHERE r.availability = 1 
            AND r.latitude IS NOT NULL
            AND r.longitude IS NOT NULL
            HAVING distance <= ?
            ORDER BY distance
            LIMIT 10
        ''', (lat, lng, lat, radius)).fetchall()
        
        # If no responders with coordinates, return available responders
        if not responders:
            responders = conn.execute('''
                SELECT * FROM responders 
                WHERE availability = 1 
                LIMIT 10
            ''').fetchall()
            
            # Add dummy distances
            responders_list = []
            for i, r in enumerate(responders):
                responder = dict(r)
                responder['distance'] = round(1.5 + i * 0.5, 1)
                responders_list.append(responder)
            
            return jsonify(responders_list)
        
        return jsonify([dict(r) for r in responders])
        
    except Exception as e:
        logger.error(f"Nearby responders error: {e}")
        return jsonify({'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/nearby_users')
@login_required
def get_nearby_users():
    """Get nearby verified users for community assistance"""
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 5, type=float)  # km
    
    if not lat or not lng:
        lat, lng = 28.6139, 77.2090  # Default to New Delhi
    
    conn = get_db_connection()
    
    try:
        # Get verified users with distance calculation
        users = conn.execute('''
            SELECT u.*,
                   ROUND(111.045 * DEGREES(ACOS(
                       COS(RADIANS(?)) * COS(RADIANS(u.latitude)) *
                       COS(RADIANS(?) - RADIANS(u.longitude)) +
                       SIN(RADIANS(?)) * SIN(RADIANS(u.latitude))
                   )), 2) as distance
            FROM users u
            WHERE u.verification_status = 'verified'
            AND u.latitude IS NOT NULL
            AND u.longitude IS NOT NULL
            AND u.id != ?
            HAVING distance <= ?
            ORDER BY distance, u.help_count DESC
            LIMIT 20
        ''', (lat, lng, lat, session['user_id'], radius)).fetchall()
        
        # If no users with coordinates, return verified users
        if not users:
            users = conn.execute('''
                SELECT * FROM users 
                WHERE verification_status = 'verified'
                AND id != ?
                LIMIT 10
            ''', (session['user_id'],)).fetchall()
            
            # Add dummy distances
            users_list = []
            for i, u in enumerate(users):
                user = dict(u)
                user['distance'] = round(0.5 + i * 0.3, 1)
                users_list.append(user)
            
            return jsonify(users_list)
        
        return jsonify([dict(u) for u in users])
        
    except Exception as e:
        logger.error(f"Nearby users error: {e}")
        return jsonify({'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/admin/stats')
@role_required('admin')
def admin_stats():
    """Get admin dashboard statistics"""
    conn = get_db_connection()
    
    try:
        total_incidents = conn.execute('SELECT COUNT(*) FROM incidents').fetchone()[0]
        active_incidents = conn.execute("SELECT COUNT(*) FROM incidents WHERE status NOT IN ('resolved', 'closed')").fetchone()[0]
        total_users = conn.execute("SELECT COUNT(*) FROM users WHERE verification_status = 'verified'").fetchone()[0]
        available_responders = conn.execute("SELECT COUNT(*) FROM responders WHERE availability = 1").fetchone()[0]
        
        return jsonify({
            'success': True,
            'total_incidents': total_incidents,
            'active_incidents': active_incidents,
            'total_users': total_users,
            'available_responders': available_responders
        })
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/incidents/<int:incident_id>/approve', methods=['POST'])
@role_required('admin')
def approve_incident(incident_id):
    """Approve an incident"""
    conn = get_db_connection()
    
    try:
        conn.execute('UPDATE incidents SET status = ? WHERE id = ?', ('approved', incident_id))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (incident_id, 'incident_approved', str(session['user_id']), 'admin'))
        
        conn.commit()
        
        # Notify via Socket.IO
        socketio.emit('incident_update', {
            'id': incident_id,
            'status': 'approved',
            'updated_by': session['username']
        })
        
        return jsonify({'success': True, 'message': 'Incident approved'})
        
    except Exception as e:
        logger.error(f"Approve incident error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/assign_responder', methods=['POST'])
@role_required('admin')
def assign_responder_api():
    """Assign a responder to an incident"""
    data = request.json
    incident_id = data.get('incident_id')
    responder_id = data.get('responder_id')
    
    if not incident_id or not responder_id:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
    
    conn = get_db_connection()
    
    try:
        # Update incident status
        conn.execute('UPDATE incidents SET status = ? WHERE id = ?', ('dispatched', incident_id))
        
        # Create assignment
        conn.execute('''
            INSERT INTO assignments (incident_id, assignee_id, assignee_type, status)
            VALUES (?, ?, ?, ?)
        ''', (incident_id, responder_id, 'responder', 'assigned'))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (incident_id, 'responder_assigned', str(session['user_id']), 'admin'))
        
        # Update responder incidents count
        conn.execute('UPDATE responders SET incidents_handled = incidents_handled + 1 WHERE id = ?', (responder_id,))
        
        conn.commit()
        
        # Notify via Socket.IO
        socketio.emit('incident_update', {
            'id': incident_id,
            'status': 'dispatched',
            'assigned_to': responder_id
        })
        
        # Notify responder
        socketio.emit('responder_assigned', {
            'incident_id': incident_id,
            'responder_id': responder_id,
            'emergency_type': data.get('emergency_type', 'emergency'),
            'location': data.get('location', {'lat': 28.6139, 'lng': 77.2090})
        })
        
        return jsonify({'success': True, 'message': 'Responder assigned'})
        
    except Exception as e:
        logger.error(f"Assign responder error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/incidents/assign', methods=['POST'])
@role_required('admin')
def assign_responder_legacy():
    """Legacy endpoint for assigning responders (for backward compatibility)"""
    data = request.json
    incident_id = data.get('incident_id')
    responder_id = data.get('responder_id')
    
    if not incident_id or not responder_id:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
    conn = get_db_connection()
    try:
        # Check incident and responder exist
        incident = conn.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,)).fetchone()
        responder = conn.execute('SELECT * FROM responders WHERE id = ?', (responder_id,)).fetchone()
        
        if not incident or not responder:
            return jsonify({'success': False, 'error': 'Incident or Responder not found'}), 404
            
        # Create assignment
        conn.execute('''
            INSERT INTO assignments (incident_id, assignee_id, assignee_type, status)
            VALUES (?, ?, 'responder', 'assigned')
        ''', (incident_id, responder_id))
        
        # Update incident status
        conn.execute('''
            UPDATE incidents SET status = 'dispatched' WHERE id = ?
        ''', (incident_id,))
        
        # Log action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, 'responder_assigned', ?, 'admin')
        ''', (incident_id, session['user_id']))
        
        conn.commit()
        
        # Notify Responder
        socketio.emit('incident_assigned', {
            'incident_id': incident_id,
            'responder_id': responder_id,
            'incident_type': incident['emergency_type'],
            'location': {'lat': incident['latitude'], 'lng': incident['longitude']}
        })
        
        # Notify Admin/Citizens of status change
        socketio.emit('status_change', {
            'incident_id': incident_id,
            'new_status': 'dispatched',
            'updated_by': 'Admin'
        })
        
        return jsonify({'success': True, 'message': 'Responder assigned successfully'})
        
    except Exception as e:
        logger.error(f"Assignment error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/responders/<int:responder_id>/availability', methods=['POST'])
@role_required('admin')
def update_responder_availability(responder_id):
    """Update responder availability"""
    data = request.json
    available = data.get('available', True)
    
    conn = get_db_connection()
    
    try:
        conn.execute('UPDATE responders SET availability = ? WHERE id = ?', (available, responder_id))
        conn.commit()
        
        # Emit socket event
        socketio.emit('responder_availability', {
            'responder_id': responder_id,
            'available': available
        })
        
        return jsonify({'success': True, 'message': 'Availability updated'})
        
    except Exception as e:
        logger.error(f"Update availability error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/quick_emergency', methods=['POST'])
@role_required('admin')
def quick_emergency():
    """Create a quick emergency (admin initiated)"""
    data = request.json
    emergency_type = data.get('emergency_type')
    description = data.get('description', '')
    
    if not emergency_type:
        return jsonify({'success': False, 'error': 'Emergency type required'}), 400
    
    # Use default location for demo
    lat, lng = 28.6139, 77.2090
    
    conn = get_db_connection()
    
    try:
        # AI classification
        severity = classify_incident(emergency_type, description)
        
        # Create incident with admin as reporter (user_id = 0 for admin-created)
        cursor = conn.execute('''
            INSERT INTO incidents (user_id, emergency_type, description, severity, status, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (0, emergency_type, description, severity, 'reported', lat, lng))
        
        incident_id = cursor.lastrowid
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (incident_id, 'incident_created_by_admin', str(session['user_id']), 'admin'))
        
        conn.commit()
        
        # Notify via Socket.IO
        socketio.emit('new_incident', {
            'id': incident_id,
            'type': emergency_type,
            'severity': severity,
            'location': {'lat': lat, 'lng': lng},
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True, 
            'incident_id': incident_id,
            'message': 'Emergency created successfully!'
        })
        
    except Exception as e:
        logger.error(f"Quick emergency error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/update_location', methods=['POST'])
@login_required
def update_user_location():
    """Update user's location"""
    data = request.json
    user_id = session['user_id']
    user_type = session['user_type']
    
    conn = get_db_connection()
    
    try:
        update_fields = []
        update_values = []
        
        if 'latitude' in data and 'longitude' in data:
            update_fields.append('latitude = ?')
            update_fields.append('longitude = ?')
            update_values.extend([data['latitude'], data['longitude']])
        
        if 'is_sharing' in data:
            update_fields.append('is_sharing_location = ?')
            update_values.append(data['is_sharing'])
        
        if update_fields:
            update_values.append(user_id)
            
            if user_type == 'citizen':
                query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
            elif user_type == 'responder':
                query = f"UPDATE responders SET {', '.join(update_fields)} WHERE id = ?"
            else:
                return jsonify({'success': False, 'error': 'Invalid user type'}), 400
            
            conn.execute(query, update_values)
            
            # Log location history
            if 'latitude' in data and 'longitude' in data:
                conn.execute('''
                    INSERT INTO user_location_history (user_id, user_type, latitude, longitude)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, user_type, data['latitude'], data['longitude']))
            
            conn.commit()
        
        # Emit location update
        if 'latitude' in data and 'longitude' in data:
            if user_type == 'citizen':
                socketio.emit('citizen_location_update', {
                    'user_id': user_id,
                    'user_name': session['username'],
                    'lat': data['latitude'],
                    'lng': data['longitude']
                })
            elif user_type == 'responder':
                socketio.emit('responder_location_update', {
                    'responder_id': user_id,
                    'responder_name': session['username'],
                    'lat': data['latitude'],
                    'lng': data['longitude']
                })
        
        return jsonify({'success': True, 'message': 'Location updated'})
        
    except Exception as e:
        logger.error(f"Update location error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/nearby_incidents')
@login_required
def nearby_incidents():
    """Get incidents near user's location"""
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 5, type=float)  # km
    
    if not lat or not lng:
        lat, lng = 28.6139, 77.2090
    
    conn = get_db_connection()
    
    try:
        # Get incidents with distance calculation
        incidents = conn.execute('''
            SELECT i.*, u.name as user_name,
                   ROUND(111.045 * DEGREES(ACOS(
                       COS(RADIANS(?)) * COS(RADIANS(i.latitude)) *
                       COS(RADIANS(?) - RADIANS(i.longitude)) +
                       SIN(RADIANS(?)) * SIN(RADIANS(i.latitude))
                   )), 2) as distance
            FROM incidents i
            JOIN users u ON i.user_id = u.id
            WHERE i.status NOT IN ('resolved', 'closed')
            AND i.latitude IS NOT NULL
            AND i.longitude IS NOT NULL
            HAVING distance <= ?
            ORDER BY distance, i.created_at DESC
            LIMIT 20
        ''', (lat, lng, lat, radius)).fetchall()
        
        # If no incidents with coordinates, return recent incidents
        if not incidents:
            incidents = conn.execute('''
                SELECT i.*, u.name as user_name
                FROM incidents i
                JOIN users u ON i.user_id = u.id
                WHERE i.status NOT IN ('resolved', 'closed')
                ORDER BY i.created_at DESC
                LIMIT 20
            ''').fetchall()
            
            # Add dummy distances
            incidents_list = []
            for i, incident in enumerate(incidents):
                incident_dict = dict(incident)
                incident_dict['distance'] = round(0.5 + i * 0.3, 1)
                incidents_list.append(incident_dict)
            
            return jsonify({
                'success': True,
                'incidents': incidents_list,
                'count': len(incidents_list)
            })
        
        incidents_list = [dict(incident) for incident in incidents]
        return jsonify({
            'success': True,
            'incidents': incidents_list,
            'count': len(incidents_list)
        })
        
    except Exception as e:
        logger.error(f"Nearby incidents error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/nearby_help_requests')
@login_required
def nearby_help_requests():
    """Get help requests near user for community assistance"""
    user_id = session['user_id']
    user_type = session['user_type']
    
    if user_type != 'citizen':
        return jsonify({'success': False, 'error': 'Only citizens can view help requests'}), 403
    
    conn = get_db_connection()
    
    try:
        # Get user's location
        user = conn.execute('SELECT latitude, longitude FROM users WHERE id = ?', (user_id,)).fetchone()
        
        if not user or not user['latitude'] or not user['longitude']:
            return jsonify({'success': True, 'requests': [], 'count': 0})
        
        # Get incidents that need community help (status is approved and no responder assigned)
        incidents = conn.execute('''
            SELECT i.*, u.name as user_name,
                   ROUND(111.045 * DEGREES(ACOS(
                       COS(RADIANS(?)) * COS(RADIANS(i.latitude)) *
                       COS(RADIANS(?) - RADIANS(i.longitude)) +
                       SIN(RADIANS(?)) * SIN(RADIANS(i.latitude))
                   )), 2) as distance
            FROM incidents i
            JOIN users u ON i.user_id = u.id
            WHERE i.status = 'approved'
            AND NOT EXISTS (
                SELECT 1 FROM assignments a 
                WHERE a.incident_id = i.id 
                AND a.assignee_type = 'responder'
            )
            AND i.user_id != ?
            AND i.latitude IS NOT NULL
            AND i.longitude IS NOT NULL
            HAVING distance <= 5
            ORDER BY distance, i.created_at DESC
            LIMIT 10
        ''', (user['latitude'], user['longitude'], user['latitude'], user_id)).fetchall()
        
        # Check which incidents already have community assignments for this user
        requests_list = []
        for incident in incidents:
            incident_dict = dict(incident)
            
            # Check if user is already assigned to this incident
            existing_assignment = conn.execute('''
                SELECT * FROM community_assignments 
                WHERE incident_id = ? AND user_id = ?
            ''', (incident_dict['id'], user_id)).fetchone()
            
            if not existing_assignment:
                requests_list.append(incident_dict)
        
        return jsonify({
            'success': True,
            'requests': requests_list,
            'count': len(requests_list)
        })
        
    except Exception as e:
        logger.error(f"Help requests error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/assess_severity', methods=['POST'])
@login_required
def assess_severity():
    """AI assessment of emergency severity"""
    data = request.json
    emergency_type = data.get('emergency_type', '')
    description = data.get('description', '')
    
    if not emergency_type:
        return jsonify({'success': False, 'error': 'Emergency type required'}), 400
    
    # Base severity from classification
    severity = classify_incident(emergency_type, description)
    
    # Adjust based on additional factors
    additional_factors = {
        'people_affected': data.get('people_affected', ''),
        'immediate_danger': data.get('immediate_danger', ''),
        'can_assist': data.get('can_assist', 'no')
    }
    
    # Adjust severity based on additional factors
    if additional_factors['immediate_danger'] in ['fire', 'structural', 'chemical', 'weapon']:
        if severity != 'critical':
            severity = 'high'
    
    if additional_factors['people_affected'] in ['6-10', '10+']:
        if severity == 'low':
            severity = 'medium'
        elif severity == 'medium':
            severity = 'high'
    
    if additional_factors['can_assist'] == 'no' and severity == 'low':
        severity = 'medium'
    
    # Calculate confidence (simulated for demo)
    confidence = 0.8  # 80% confidence
    
    # Increase confidence with more details
    if description and len(description) > 20:
        confidence = min(0.95, confidence + 0.1)
    
    if additional_factors['people_affected'] and additional_factors['immediate_danger']:
        confidence = min(0.98, confidence + 0.15)
    
    return jsonify({
        'success': True,
        'severity': severity,
        'confidence': confidence,
        'factors_considered': [
            'emergency_type',
            'description_analysis',
            'people_affected' if additional_factors['people_affected'] else None,
            'immediate_danger' if additional_factors['immediate_danger'] else None,
            'assistance_availability'
        ]
    })

@app.route('/api/accept_help_request/<int:incident_id>', methods=['POST'])
@role_required('citizen')
def accept_help_request(incident_id):
    """Citizen accepts a help request"""
    conn = get_db_connection()
    
    try:
        # Check if incident exists and needs help
        incident = conn.execute('''
            SELECT * FROM incidents 
            WHERE id = ? AND status = 'approved'
        ''', (incident_id,)).fetchone()
        
        if not incident:
            return jsonify({'success': False, 'error': 'Incident not found or already handled'}), 404
        
        # Check if user is already assigned
        existing = conn.execute('''
            SELECT * FROM assignments 
            WHERE incident_id = ? AND assignee_id = ? AND assignee_type = 'user'
        ''', (incident_id, session['user_id'])).fetchone()
        
        if existing:
            return jsonify({'success': False, 'error': 'Already assigned to this incident'}), 400
        
        # Create assignment
        conn.execute('''
            INSERT INTO assignments (incident_id, assignee_id, assignee_type, status)
            VALUES (?, ?, 'user', 'accepted')
        ''', (incident_id, session['user_id']))
        
        # Update user's help count
        conn.execute('UPDATE users SET help_count = help_count + 1 WHERE id = ?', (session['user_id'],))
        
        # Add points
        conn.execute('UPDATE users SET points = points + 10 WHERE id = ?', (session['user_id'],))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (incident_id, 'help_request_accepted', str(session['user_id']), 'citizen'))
        
        conn.commit()
        
        # Notify via Socket.IO
        socketio.emit('help_accepted', {
            'incident_id': incident_id,
            'helper_id': session['user_id'],
            'helper_name': session['username']
        })
        
        return jsonify({
            'success': True,
            'message': 'Help request accepted successfully',
            'incident_id': incident_id
        })
        
    except Exception as e:
        logger.error(f"Accept help request error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/assign_responder', methods=['POST'])
@role_required('admin')
def assign_responder():
    """Assign a professional responder to an incident"""
    data = request.json
    incident_id = data.get('incident_id')
    responder_id = data.get('responder_id')
    
    if not incident_id or not responder_id:
        return jsonify({'success': False, 'error': 'Incident ID and Responder ID are required'}), 400
    
    conn = get_db_connection()
    
    try:
        # Check if incident exists
        incident = conn.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,)).fetchone()
        if not incident:
            return jsonify({'success': False, 'error': 'Incident not found'}), 404
        
        # Check if responder exists and is available
        responder = conn.execute('SELECT * FROM responders WHERE id = ?', (responder_id,)).fetchone()
        if not responder:
            return jsonify({'success': False, 'error': 'Responder not found'}), 404
            
        # Check if already assigned
        existing = conn.execute('''
            SELECT * FROM assignments 
            WHERE incident_id = ? AND assignee_id = ? AND assignee_type = 'responder'
        ''', (incident_id, responder_id)).fetchone()
        
        if existing:
            return jsonify({'success': False, 'error': 'Responder already assigned to this incident'}), 400
        
        # Create assignment
        conn.execute('''
            INSERT INTO assignments (incident_id, assignee_id, assignee_type, status)
            VALUES (?, ?, 'responder', 'assigned')
        ''', (incident_id, responder_id))
        
        # Update incident status to dispatched
        conn.execute('''
            UPDATE incidents SET status = 'dispatched' WHERE id = ?
        ''', (incident_id,))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (incident_id, 'responder_assigned', str(session['user_id']), 'admin'))
        
        conn.commit()
        
        # Notify via Socket.IO
        socketio.emit('responder_assigned', {
            'incident_id': incident_id,
            'responder_id': responder_id,
            'responder_name': responder['name'],
            'incident_type': incident['emergency_type']
        })
        
        # Notify the responder specifically (if they are online)
        socketio.emit('new_assignment', {
            'incident_id': incident_id,
            'type': incident['emergency_type'],
            'severity': incident['severity'],
            'location': {'lat': incident['latitude'], 'lng': incident['longitude']},
            'description': incident['description']
        }) # This would ideally be targeted to the specific responder room
        
        return jsonify({
            'success': True,
            'message': f'Responder {responder["name"]} assigned successfully',
            'incident_id': incident_id
        })
        
    except Exception as e:
        logger.error(f"Assign responder error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/assign_community_helpers', methods=['POST'])
@role_required('admin')
def assign_community_helpers_api():
    """API to assign community helpers to an incident"""
    data = request.json
    incident_id = data.get('incident_id')
    selected_users = data.get('selected_users', '').split(',')
    instructions = data.get('instructions', '')
    
    if not incident_id or not selected_users or selected_users == ['']:
        return jsonify({'success': False, 'error': 'No users selected'}), 400
    
    conn = get_db_connection()
    
    try:
        # Get incident details
        incident = conn.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,)).fetchone()
        if not incident:
            return jsonify({'success': False, 'error': 'Incident not found'}), 404
        
        # Create community assignments
        user_ids = [int(uid) for uid in selected_users if uid]
        
        for user_id in user_ids:
            # Check if user already assigned
            existing = conn.execute('''
                SELECT * FROM community_assignments 
                WHERE incident_id = ? AND user_id = ?
            ''', (incident_id, user_id)).fetchone()
            
            if not existing:
                conn.execute('''
                    INSERT INTO community_assignments 
                    (incident_id, user_id, status, notes)
                    VALUES (?, ?, 'requested', ?)
                ''', (incident_id, user_id, instructions))
                
                # Update incident status if not already dispatched
                if incident['status'] == 'approved':
                    conn.execute('''
                        UPDATE incidents SET status = 'community_dispatched' WHERE id = ?
                    ''', (incident_id,))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (incident_id, 'community_helpers_assigned', str(session['user_id']), 'admin'))
        
        conn.commit()
        
        # Send notifications via Socket.IO
        for user_id in user_ids:
            socketio.emit('help_request', {
                'incident_id': incident_id,
                'user_id': user_id,
                'emergency_type': incident['emergency_type'],
                'severity': incident['severity'],
                'location': {'lat': incident['latitude'], 'lng': incident['longitude']},
                'instructions': instructions
            })
        
        return jsonify({
            'success': True, 
            'message': f'Help requests sent to {len(user_ids)} user(s)',
            'incident_id': incident_id
        })
        
    except Exception as e:
        logger.error(f"Assign community helpers error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/community_assignment/<int:assignment_id>/accept', methods=['POST'])
@role_required('citizen')
def accept_community_assignment(assignment_id):
    """Citizen accepts a community assignment"""
    conn = get_db_connection()
    
    try:
        # Get assignment details
        assignment = conn.execute('''
            SELECT ca.*, i.emergency_type, i.severity, i.latitude, i.longitude
            FROM community_assignments ca
            JOIN incidents i ON ca.incident_id = i.id
            WHERE ca.id = ? AND ca.user_id = ?
        ''', (assignment_id, session['user_id'])).fetchone()
        
        if not assignment:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404
        
        if assignment['status'] != 'requested':
            return jsonify({'success': False, 'error': 'Assignment already processed'}), 400
        
        # Update assignment status
        conn.execute('''
            UPDATE community_assignments 
            SET status = 'accepted', accepted_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (assignment_id,))
        
        # Update user's help count
        conn.execute('UPDATE users SET help_count = help_count + 1 WHERE id = ?', (session['user_id'],))
        
        # Add points for acceptance
        conn.execute('UPDATE users SET points = points + 10 WHERE id = ?', (session['user_id'],))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (assignment['incident_id'], 'community_help_accepted', str(session['user_id']), 'citizen'))
        
        conn.commit()
        
        # Notify admin via Socket.IO
        socketio.emit('help_accepted', {
            'incident_id': assignment['incident_id'],
            'user_id': session['user_id'],
            'user_name': session['username'],
            'assignment_id': assignment_id
        })
        
        return jsonify({
            'success': True,
            'message': 'Help request accepted! Navigate to the emergency location.',
            'location': {
                'lat': assignment['latitude'],
                'lng': assignment['longitude']
            }
        })
        
    except Exception as e:
        logger.error(f"Accept community assignment error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/community_assignment/<int:assignment_id>/decline', methods=['POST'])
@role_required('citizen')
def decline_community_assignment(assignment_id):
    """Citizen declines a community assignment"""
    conn = get_db_connection()
    
    try:
        # Check assignment
        assignment = conn.execute('''
            SELECT * FROM community_assignments 
            WHERE id = ? AND user_id = ?
        ''', (assignment_id, session['user_id'])).fetchone()
        
        if not assignment:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404
        
        if assignment['status'] != 'requested':
            return jsonify({'success': False, 'error': 'Assignment already processed'}), 400
        
        # Update assignment status
        conn.execute('''
            UPDATE community_assignments 
            SET status = 'declined'
            WHERE id = ?
        ''', (assignment_id,))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (assignment['incident_id'], 'community_help_declined', str(session['user_id']), 'citizen'))
        
        conn.commit()
        
        # Notify admin (optional)
        socketio.emit('help_declined', {
            'incident_id': assignment['incident_id'],
            'user_id': session['user_id'],
            'user_name': session['username']
        })
        
        return jsonify({
            'success': True,
            'message': 'Help request declined'
        })
        
    except Exception as e:
        logger.error(f"Decline community assignment error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/community_assignment/<int:assignment_id>/arrived', methods=['POST'])
@login_required
def mark_community_helper_arrived(assignment_id):
    """Mark community helper as arrived at scene"""
    conn = get_db_connection()
    
    try:
        user_type = session['user_type']
        
        if user_type == 'citizen':
            # Citizen marking themselves arrived
            assignment = conn.execute('''
                SELECT * FROM community_assignments 
                WHERE id = ? AND user_id = ?
            ''', (assignment_id, session['user_id'])).fetchone()
            
            if not assignment:
                return jsonify({'success': False, 'error': 'Assignment not found'}), 404
            
            conn.execute('''
                UPDATE community_assignments 
                SET status = 'arrived', arrived_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (assignment_id,))
            
        elif user_type == 'admin':
            # Admin marking helper arrived
            conn.execute('''
                UPDATE community_assignments 
                SET status = 'arrived', arrived_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (assignment_id,))
        
        else:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Log the action
        assignment = conn.execute('SELECT incident_id FROM community_assignments WHERE id = ?', (assignment_id,)).fetchone()
        if assignment:
            conn.execute('''
                INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
                VALUES (?, ?, ?, ?)
            ''', (assignment['incident_id'], 'community_helper_arrived', str(session['user_id']), session['user_type']))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Marked as arrived at scene'
        })
        
    except Exception as e:
        logger.error(f"Mark arrived error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/map/incidents')
@role_required('admin')
def map_incidents():
    """Get incidents for map display"""
    conn = get_db_connection()
    
    try:
        incidents = conn.execute('''
            SELECT i.*, u.name as user_name, u.phone as user_phone
            FROM incidents i
            LEFT JOIN users u ON i.user_id = u.id
            ORDER BY i.created_at DESC
        ''').fetchall()
        
        incidents_list = []
        for incident in incidents:
            incident_dict = dict(incident)
            incidents_list.append(incident_dict)
        
        return jsonify({
            'success': True,
            'incidents': incidents_list,
            'count': len(incidents_list)
        })
        
    except Exception as e:
        logger.error(f"Map incidents error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/map/responders')
@role_required('admin')
def map_responders():
    """Get responders for map display"""
    conn = get_db_connection()
    
    try:
        responders = conn.execute('''
            SELECT * FROM responders 
            WHERE availability = 1 
            AND latitude IS NOT NULL 
            AND longitude IS NOT NULL
        ''').fetchall()
        
        responders_list = []
        for responder in responders:
            responder_dict = dict(responder)
            responders_list.append(responder_dict)
        
        return jsonify({
            'success': True,
            'responders': responders_list,
            'count': len(responders_list)
        })
        
    except Exception as e:
        logger.error(f"Map responders error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/incidents/<int:incident_id>/location')
@role_required('admin')
def incident_location(incident_id):
    """Get incident location for map"""
    conn = get_db_connection()
    
    try:
        incident = conn.execute('''
            SELECT latitude, longitude, emergency_type, severity, status
            FROM incidents WHERE id = ?
        ''', (incident_id,)).fetchone()
        
        if not incident:
            return jsonify({'success': False, 'error': 'Incident not found'}), 404
        
        return jsonify({
            'success': True,
            'location': {
                'lat': incident['latitude'],
                'lng': incident['longitude'],
                'type': incident['emergency_type'],
                'severity': incident['severity'],
                'status': incident['status']
            }
        })
        
    except Exception as e:
        logger.error(f"Incident location error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/leaderboard')
@login_required
def leaderboard():
    """Leaderboard page"""
    conn = get_db_connection()
    
    try:
        user_type = session['user_type']
        user_id = session['user_id']
        
        # Citizen leaderboard
        citizen_leaderboard = conn.execute('''
            SELECT id, name, email, help_count, points, created_at,
                   ROW_NUMBER() OVER (ORDER BY points DESC, help_count DESC) as rank
            FROM users 
            WHERE verification_status = 'verified'
            ORDER BY points DESC, help_count DESC
            LIMIT 100
        ''').fetchall()
        
        # Responder leaderboard
        responder_leaderboard = conn.execute('''
            SELECT id, name, email, role, incidents_handled, response_score, availability,
                   ROW_NUMBER() OVER (ORDER BY response_score DESC, incidents_handled DESC) as rank
            FROM responders 
            ORDER BY response_score DESC, incidents_handled DESC
            LIMIT 50
        ''').fetchall()
        
        # Get user's position
        user_position = None
        if user_type == 'citizen':
            for i, citizen in enumerate(citizen_leaderboard, 1):
                if citizen['id'] == user_id:
                    user_position = {'rank': i, 'points': citizen['points'], 'help_count': citizen['help_count']}
                    break
        
        # Get user details
        user = None
        if user_type == 'citizen':
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        elif user_type == 'responder':
            user = conn.execute('SELECT * FROM responders WHERE id = ?', (user_id,)).fetchone()
        
        # Monthly top performers (simplified - using last 30 days)
        monthly_citizens = conn.execute('''
            SELECT u.id, u.name, u.points, u.help_count,
                   (SELECT COUNT(*) FROM community_assignments ca 
                    WHERE ca.user_id = u.id 
                    AND ca.accepted_at >= date('now', '-30 days')) as monthly_helps,
                   (SELECT COUNT(*) * 10 FROM community_assignments ca 
                    WHERE ca.user_id = u.id 
                    AND ca.status = 'completed'
                    AND ca.completed_at >= date('now', '-30 days')) as monthly_points
            FROM users u
            WHERE u.verification_status = 'verified'
            ORDER BY monthly_points DESC
            LIMIT 10
        ''').fetchall()
        
        monthly_responders = conn.execute('''
            SELECT r.id, r.name, r.role, r.incidents_handled, r.response_score,
                   (SELECT COUNT(*) FROM assignments a 
                    JOIN incidents i ON a.incident_id = i.id
                    WHERE a.assignee_id = r.id 
                    AND a.assignee_type = 'responder'
                    AND i.resolved_at >= date('now', '-30 days')) as monthly_incidents,
                   (SELECT COUNT(*) * 15 FROM assignments a 
                    JOIN incidents i ON a.incident_id = i.id
                    WHERE a.assignee_id = r.id 
                    AND a.assignee_type = 'responder'
                    AND i.resolved_at >= date('now', '-30 days')) as monthly_score
            FROM responders r
            ORDER BY monthly_score DESC
            LIMIT 10
        ''').fetchall()
        
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        flash('Error loading leaderboard', 'danger')
        return redirect(url_for('index'))
    
    finally:
        conn.close()
    
    return render_template('leaderboard.html',
                         citizen_leaderboard=citizen_leaderboard,
                         responder_leaderboard=responder_leaderboard,
                         user_position=user_position,
                         user=user,
                         monthly_citizens=monthly_citizens,
                         monthly_responders=monthly_responders)

# ==================== SOCKET.IO EVENTS ====================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to emergency system'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('location_update')
def handle_location_update(data):
    """Update user location"""
    user_id = session.get('user_id')
    user_type = session.get('user_type')
    
    if not user_id:
        return
    
    conn = get_db_connection()
    
    try:
        if user_type == 'citizen':
            conn.execute('''
                UPDATE users 
                SET latitude = ?, longitude = ?
                WHERE id = ?
            ''', (data.get('lat'), data.get('lng'), user_id))
        elif user_type == 'responder':
            conn.execute('''
                UPDATE responders 
                SET latitude = ?, longitude = ?
                WHERE id = ?
            ''', (data.get('lat'), data.get('lng'), user_id))
        
        conn.commit()
        
        # Broadcast location update
        if user_type == 'citizen':
            socketio.emit('citizen_location_update', {
                'user_id': user_id,
                'user_name': session.get('username'),
                'lat': data.get('lat'),
                'lng': data.get('lng')
            })
        elif user_type == 'responder':
            socketio.emit('responder_location_update', {
                'responder_id': user_id,
                'responder_name': session.get('username'),
                'lat': data.get('lat'),
                'lng': data.get('lng')
            })
        
    except Exception as e:
        logger.error(f"Location update error: {e}")
    
    finally:
        conn.close()

@socketio.on('help_request_accepted')
def handle_help_accepted(data):
    """Broadcast when a citizen accepts a help request"""
    socketio.emit('help_request_accepted_broadcast', data)

@socketio.on('community_helper_location')
def handle_community_helper_location(data):
    """Update community helper location"""
    user_id = session.get('user_id')
    user_type = session.get('user_type')
    
    if user_type != 'citizen':
        return
    
    conn = get_db_connection()
    
    try:
        # Update user location
        conn.execute('''
            UPDATE users 
            SET latitude = ?, longitude = ?
            WHERE id = ?
        ''', (data.get('lat'), data.get('lng'), user_id))
        
        # Log location history
        conn.execute('''
            INSERT INTO user_location_history (user_id, user_type, latitude, longitude)
            VALUES (?, ?, ?, ?)
        ''', (user_id, user_type, data.get('lat'), data.get('lng')))
        
        conn.commit()
        
        # Broadcast to admin
        socketio.emit('community_helper_location_update', {
            'user_id': user_id,
            'user_name': session.get('username'),
            'lat': data.get('lat'),
            'lng': data.get('lng')
        })
        
    except Exception as e:
        logger.error(f"Community helper location error: {e}")
    
    finally:
        conn.close()

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# Add these routes to app.py after the existing routes

@app.route('/api/community/assignments')
@login_required
def get_community_assignments():
    """Get community assignments for the current user"""
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    
    if user_type != 'citizen':
        return jsonify({'success': False, 'error': 'Only citizens can view community assignments'}), 403
    
    conn = get_db_connection()
    
    try:
        assignments = conn.execute('''
            SELECT ca.*, i.emergency_type, i.severity, i.description, 
                   i.latitude, i.longitude, i.status as incident_status,
                   u_reporter.name as reporter_name
            FROM community_assignments ca
            JOIN incidents i ON ca.incident_id = i.id
            JOIN users u_reporter ON i.user_id = u_reporter.id
            WHERE ca.user_id = ?
            ORDER BY ca.requested_at DESC
        ''', (user_id,)).fetchall()
        
        assignments_list = []
        for assignment in assignments:
            assignment_dict = dict(assignment)
            assignments_list.append(assignment_dict)
        
        return jsonify({
            'success': True,
            'assignments': assignments_list,
            'count': len(assignments_list)
        })
        
    except Exception as e:
        logger.error(f"Get community assignments error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/community/assignment/<int:assignment_id>')
@login_required
def get_community_assignment(assignment_id):
    """Get specific community assignment details"""
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    
    try:
        assignment = conn.execute('''
            SELECT ca.*, i.*, u_reporter.name as reporter_name, 
                   u_reporter.phone as reporter_phone,
                   (SELECT COUNT(*) FROM community_assignments ca2 
                    WHERE ca2.incident_id = i.id AND ca2.status = 'accepted') as accepted_helpers_count
            FROM community_assignments ca
            JOIN incidents i ON ca.incident_id = i.id
            JOIN users u_reporter ON i.user_id = u_reporter.id
            WHERE ca.id = ? AND ca.user_id = ?
        ''', (assignment_id, user_id)).fetchone()
        
        if not assignment:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404
        
        assignment_dict = dict(assignment)
        
        # Get other helpers assigned to same incident
        other_helpers = conn.execute('''
            SELECT ca.*, u.name as helper_name
            FROM community_assignments ca
            JOIN users u ON ca.user_id = u.id
            WHERE ca.incident_id = ? AND ca.user_id != ? AND ca.status IN ('accepted', 'arrived')
            ORDER BY ca.accepted_at
        ''', (assignment_dict['incident_id'], user_id)).fetchall()
        
        assignment_dict['other_helpers'] = [dict(helper) for helper in other_helpers]
        
        return jsonify({
            'success': True,
            'assignment': assignment_dict
        })
        
    except Exception as e:
        logger.error(f"Get community assignment error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/community/assignment/<int:assignment_id>/complete', methods=['POST'])
@login_required
def complete_community_assignment(assignment_id):
    """Mark community assignment as completed"""
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    
    if user_type != 'citizen':
        return jsonify({'success': False, 'error': 'Only citizens can complete assignments'}), 403
    
    conn = get_db_connection()
    
    try:
        # Check assignment exists and belongs to user
        assignment = conn.execute('''
            SELECT * FROM community_assignments 
            WHERE id = ? AND user_id = ?
        ''', (assignment_id, user_id)).fetchone()
        
        if not assignment:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404
        
        if assignment['status'] not in ['accepted', 'arrived']:
            return jsonify({'success': False, 'error': 'Assignment must be accepted or arrived first'}), 400
        
        # Update assignment status
        conn.execute('''
            UPDATE community_assignments 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (assignment_id,))
        
        # Add points for completion
        points_earned = 20  # More points for completing
        conn.execute('''
            UPDATE users 
            SET points = points + ?, help_count = help_count + 1
            WHERE id = ?
        ''', (points_earned, user_id))
        
        # Log the action
        conn.execute('''
            INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
            VALUES (?, ?, ?, ?)
        ''', (assignment['incident_id'], 'community_help_completed', str(user_id), 'citizen'))
        
        # Check if all community assignments are completed
        active_assignments = conn.execute('''
            SELECT COUNT(*) FROM community_assignments 
            WHERE incident_id = ? AND status IN ('accepted', 'arrived')
        ''', (assignment['incident_id'],)).fetchone()[0]
        
        if active_assignments == 0:
            # All community helpers completed, mark incident for review
            conn.execute('''
                UPDATE incidents SET status = 'community_completed' WHERE id = ?
            ''', (assignment['incident_id'],))
        
        conn.commit()
        
        # Send notification via Socket.IO
        socketio.emit('assignment_completed', {
            'assignment_id': assignment_id,
            'user_id': user_id,
            'user_name': session.get('username'),
            'incident_id': assignment['incident_id'],
            'points_earned': points_earned
        })
        
        return jsonify({
            'success': True,
            'message': 'Assignment completed successfully!',
            'points_earned': points_earned
        })
        
    except Exception as e:
        logger.error(f"Complete community assignment error: {e}")
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/user/stats')
@login_required
def get_user_stats():
    """Get user statistics for dashboard"""
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    
    try:
        if user_type == 'citizen':
            user = conn.execute('''
                SELECT points, help_count FROM users WHERE id = ?
            ''', (user_id,)).fetchone()
            
            # Calculate rank
            rank = None
            if user and user['points']:
                higher_count = conn.execute('''
                    SELECT COUNT(*) FROM users 
                    WHERE verification_status = 'verified' 
                    AND points > ?
                ''', (user['points'],)).fetchone()[0]
                rank = higher_count + 1
            
            return jsonify({
                'success': True,
                'points': user['points'] if user else 0,
                'help_count': user['help_count'] if user else 0,
                'rank': rank,
                'leaderboard': {
                    'rank': rank,
                    'points': user['points'] if user else 0
                }
            })
        elif user_type == 'responder':
            responder = conn.execute('''
                SELECT response_score, incidents_handled FROM responders WHERE id = ?
            ''', (user_id,)).fetchone()
            
            return jsonify({
                'success': True,
                'response_score': responder['response_score'] if responder else 0,
                'incidents_handled': responder['incidents_handled'] if responder else 0
            })
        
        return jsonify({'success': False, 'error': 'Invalid user type'}), 400
        
    except Exception as e:
        logger.error(f"Get user stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/leaderboard/top')
def get_top_leaderboard():
    """Get top performers for leaderboard"""
    conn = get_db_connection()
    
    try:
        # Top citizens
        top_citizens = conn.execute('''
            SELECT id, name, email, help_count, points,
                   ROW_NUMBER() OVER (ORDER BY points DESC, help_count DESC) as rank
            FROM users 
            WHERE verification_status = 'verified'
            ORDER BY points DESC, help_count DESC
            LIMIT 10
        ''').fetchall()
        
        # Top responders
        top_responders = conn.execute('''
            SELECT id, name, email, role, incidents_handled, response_score,
                   ROW_NUMBER() OVER (ORDER BY response_score DESC, incidents_handled DESC) as rank
            FROM responders 
            ORDER BY response_score DESC, incidents_handled DESC
            LIMIT 10
        ''').fetchall()
        
        return jsonify({
            'success': True,
            'citizens': [dict(citizen) for citizen in top_citizens],
            'responders': [dict(responder) for responder in top_responders]
        })
        
    except Exception as e:
        logger.error(f"Get top leaderboard error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/citizen/community_assignments')
@role_required('citizen')
def community_assignments():
    """Community assignments page for citizens"""
    conn = get_db_connection()
    
    try:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        # Get assignments for this user
        assignments = conn.execute('''
            SELECT ca.*, i.emergency_type, i.severity, i.description, 
                   i.latitude, i.longitude, i.status as incident_status,
                   u_reporter.name as reporter_name
            FROM community_assignments ca
            JOIN incidents i ON ca.incident_id = i.id
            JOIN users u_reporter ON i.user_id = u_reporter.id
            WHERE ca.user_id = ?
            ORDER BY ca.requested_at DESC
        ''', (session['user_id'],)).fetchall()
        
        # Separate by status for the template
        active_assignments = [a for a in assignments if a['status'] in ['accepted', 'arrived']]
        pending_assignments = [a for a in assignments if a['status'] == 'requested']
        completed_assignments = [a for a in assignments if a['status'] == 'completed']
        
    except Exception as e:
        logger.error(f"Community assignments error: {e}")
        flash('Error loading help requests', 'danger')
        return redirect(url_for('citizen_dashboard'))
    
    finally:
        conn.close()
    
    return render_template('community_assignments.html',
                         user=user,
                         active_assignments=active_assignments,
                         pending_assignments=pending_assignments,
                         completed_assignments=completed_assignments)

@socketio.on('community_helper_location')
def handle_community_helper_location(data):
    """Update community helper location"""
    user_id = session.get('user_id')
    user_type = session.get('user_type')
    
    if user_type != 'citizen':
        return
    
    conn = get_db_connection()
    
    try:
        # Update user location
        conn.execute('''
            UPDATE users 
            SET latitude = ?, longitude = ?
            WHERE id = ?
        ''', (data.get('lat'), data.get('lng'), user_id))
        
        # Log location history
        conn.execute('''
            INSERT INTO user_location_history (user_id, user_type, latitude, longitude)
            VALUES (?, ?, ?, ?)
        ''', (user_id, user_type, data.get('lat'), data.get('lng')))
        
        conn.commit()
        
        # Broadcast to admin and incident managers
        socketio.emit('community_helper_location_update', {
            'user_id': user_id,
            'user_name': session.get('username'),
            'lat': data.get('lat'),
            'lng': data.get('lng'),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Community helper location error: {e}")
    
    finally:
        conn.close()

@socketio.on('assignment_status_update')
def handle_assignment_status_update(data):
    """Update assignment status"""
    assignment_id = data.get('assignment_id')
    status = data.get('status')
    user_id = session.get('user_id')
    
    if not assignment_id or not status:
        return
    
    conn = get_db_connection()
    
    try:
        # Update assignment status
        conn.execute('''
            UPDATE community_assignments 
            SET status = ?, 
            ''' + ('accepted_at' if status == 'accepted' else 'arrived_at' if status == 'arrived' else 'completed_at') + ''' = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        ''', (status, assignment_id, user_id))
        
        # Get incident ID for notification
        assignment = conn.execute('SELECT incident_id FROM community_assignments WHERE id = ?', (assignment_id,)).fetchone()
        
        if assignment:
            # Log the action
            conn.execute('''
                INSERT INTO incident_logs (incident_id, action, performed_by, performed_role)
                VALUES (?, ?, ?, ?)
            ''', (assignment['incident_id'], f'community_assignment_{status}', str(user_id), 'citizen'))
            
            # Send notification
            socketio.emit('assignment_update', {
                'assignment_id': assignment_id,
                'user_id': user_id,
                'user_name': session.get('username'),
                'status': status,
                'incident_id': assignment['incident_id']
            })
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Assignment status update error: {e}")
    
    finally:
        conn.close()

def award_badges(user_id, user_type, action, points_earned=0):
    """Award badges based on user actions"""
    conn = get_db_connection()
    
    try:
        if user_type == 'citizen':
            # Get user's current stats
            user = conn.execute('''
                SELECT help_count, points FROM users WHERE id = ?
            ''', (user_id,)).fetchone()
            
            if not user:
                return
            
            help_count = user['help_count'] or 0
            points = user['points'] or 0
            
            badges_to_award = []
            
            # Check for badge achievements
            if help_count >= 10:
                badges_to_award.append(('hero', 'Hero Helper', 'Awarded for completing 10+ help requests'))
            elif help_count >= 5:
                badges_to_award.append(('expert', 'Expert Helper', 'Awarded for completing 5+ help requests'))
            elif help_count >= 1:
                badges_to_award.append(('helper', 'Helper', 'Awarded for completing your first help request'))
            
            # Check for first responder badge (first to accept a critical incident)
            if action == 'first_critical_response':
                badges_to_award.append(('first_responder', 'First Responder', 'Awarded for being first to accept a critical emergency'))
            
            # Award badges that haven't been awarded yet
            for badge_type, badge_name, badge_desc in badges_to_award:
                existing_badge = conn.execute('''
                    SELECT * FROM user_badges 
                    WHERE user_id = ? AND user_type = ? AND badge_type = ?
                ''', (user_id, user_type, badge_type)).fetchone()
                
                if not existing_badge:
                    conn.execute('''
                        INSERT INTO user_badges (user_id, user_type, badge_type, badge_name, description)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, user_type, badge_type, badge_name, badge_desc))
                    
                    # Send notification
                    socketio.emit('badge_earned', {
                        'user_id': user_id,
                        'user_name': session.get('username', 'User'),
                        'badge_type': badge_type,
                        'badge_name': badge_name,
                        'description': badge_desc
                    })
                    
        elif user_type == 'responder':
            # Similar logic for responders
            responder = conn.execute('''
                SELECT incidents_handled, response_score FROM responders WHERE id = ?
            ''', (user_id,)).fetchone()
            
            if not responder:
                return
            
            incidents_handled = responder['incidents_handled'] or 0
            response_score = responder['response_score'] or 0
            
            badges_to_award = []
            
            if response_score >= 100:
                badges_to_award.append(('elite', 'Elite Responder', 'Awarded for achieving 100+ response score'))
            elif incidents_handled >= 50:
                badges_to_award.append(('veteran', 'Veteran Responder', 'Awarded for handling 50+ incidents'))
            elif incidents_handled >= 10:
                badges_to_award.append(('expert', 'Expert Responder', 'Awarded for handling 10+ incidents'))
            
            # Award badges
            for badge_type, badge_name, badge_desc in badges_to_award:
                existing_badge = conn.execute('''
                    SELECT * FROM user_badges 
                    WHERE user_id = ? AND user_type = ? AND badge_type = ?
                ''', (user_id, user_type, badge_type)).fetchone()
                
                if not existing_badge:
                    conn.execute('''
                        INSERT INTO user_badges (user_id, user_type, badge_type, badge_name, description)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, user_type, badge_type, badge_name, badge_desc))
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Award badges error: {e}")
    
    finally:
        conn.close()

def calculate_monthly_performers():
    """Calculate monthly top performers"""
    conn = get_db_connection()
    
    try:
        # Get current month and year
        current_month = datetime.now().strftime('%Y-%m')
        
        # Calculate monthly points for citizens
        monthly_citizens = conn.execute('''
            SELECT u.id, u.name, u.email,
                   COALESCE(SUM(
                       CASE 
                           WHEN ca.status = 'completed' AND strftime('%Y-%m', ca.completed_at) = ? THEN 20
                           WHEN ca.status = 'accepted' AND strftime('%Y-%m', ca.accepted_at) = ? THEN 10
                           ELSE 0
                       END
                   ), 0) as monthly_points,
                   COUNT(CASE WHEN ca.status = 'completed' AND strftime('%Y-%m', ca.completed_at) = ? THEN 1 END) as monthly_helps
            FROM users u
            LEFT JOIN community_assignments ca ON u.id = ca.user_id
            WHERE u.verification_status = 'verified'
            GROUP BY u.id
            ORDER BY monthly_points DESC
            LIMIT 10
        ''', (current_month, current_month, current_month)).fetchall()
        
        # Calculate monthly stats for responders
        monthly_responders = conn.execute('''
            SELECT r.id, r.name, r.email, r.role,
                   COUNT(CASE WHEN strftime('%Y-%m', i.resolved_at) = ? THEN 1 END) as monthly_incidents,
                   COALESCE(SUM(
                       CASE 
                           WHEN strftime('%Y-%m', i.resolved_at) = ? THEN 15
                           ELSE 0
                       END
                   ), 0) as monthly_score
            FROM responders r
            LEFT JOIN assignments a ON r.id = a.assignee_id AND a.assignee_type = 'responder'
            LEFT JOIN incidents i ON a.incident_id = i.id
            GROUP BY r.id
            ORDER BY monthly_score DESC
            LIMIT 10
        ''', (current_month, current_month)).fetchall()
        
        return {
            'citizens': monthly_citizens,
            'responders': monthly_responders,
            'month': current_month
        }
        
    except Exception as e:
        logger.error(f"Calculate monthly performers error: {e}")
        return {'citizens': [], 'responders': [], 'month': current_month}
    
    finally:
        conn.close()

# ==================== MAIN ====================

if __name__ == '__main__':
    # Initialize database on startup
    init_db()
    
    logger.info("Emergency Response System starting...")
    logger.info(f"Open http://localhost:5001 in your browser")
    
    socketio.run(app, debug=app_cfg.DEBUG, host='0.0.0.0', port=5001)