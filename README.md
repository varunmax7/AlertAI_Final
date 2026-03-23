# 🚨 AlertAI: AI-Powered Emergency Response System

**AlertAI** is a comprehensive, real-time emergency incident management system designed to bridge the gap between citizens, emergency responders, and community volunteers. Using AI-driven severity classification and real-time WebSocket communication, AlertAI ensures that the right help reaches the right place at the right time.

---

## 🛠️ Tech Stack

### Backend
- **Python (Flask)**: Core application logic and API management.
- **Flask-SocketIO**: Real-time, bi-directional communication for instant alerts.
- **SQLite3**: Lightweight database for storing users, incidents, and logs.
- **Flask-Session**: Server-side session management.

### Frontend
- **HTML5/CSS3**: Responsive designs for mobile and desktop dashboards.
- **Vanilla JavaScript**: Real-time UI updates and location tracking.
- **Socket.IO Client**: Persistent connection to the server for alerts.
- **Service Workers (PWA)**: Support for installation on mobile devices.

### AI & Logic
- **Heuristic AI Engine**: Rule-based incident classification and severity assessment.
- **Haversine Algorithm**: Accurate distance calculation for proximity-based assignments.

---

## 🚀 Key Features

### 1. 📢 For Citizens
- **One-Click Reporting**: Instantly report emergencies with location coordinates.
- **AI Severity Engine**: Automatically assesses the level of danger (Critical, High, Medium, Low).
- **Community Assistance**: Join the community of verified volunteers and earn points by helping others.
- **Leaderboard**: Gamified system where users earn badges and rankings for their assistance.

### 2. 🚑 For Responders (Ambulance, Police, Fire)
- **Live Activity Feed**: View active incidents near your current location.
- **Incident Tracking**: Status-based workflow (Reported → Dispatched → Resolved).
- **Responder Dashboard**: Manage current assignments and update response status.

### 3. 🛡️ For Admins
- **Global Overview**: Unified dashboard with live statistics on total incidents, active cases, and available responders.
- **User Verification**: Secure vetting process for new citizens and responders.
- **Incident Assignment**: Manual and automated dispatch of emergency teams.

---

## 🔧 Installation & Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/varunmax7/AlertAI_Final.git
   cd AlertAI
   ```

2. **Initialize Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**:
   Create a `.env` file in the root directory:
   ```env
   SECRET_KEY=your_random_secret_key
   DEBUG=True
   ```

5. **Run the Application**:
   ```bash
   python3 app.py
   ```
   *Visit `http://127.0.0.1:5000` in your browser.*

---

## ☁️ Deployment (Vercel)

This project is configured for cloud deployment on **Vercel**.

1. Create a `vercel.json` in the root (already included).
2. Push your project to a GitHub repository.
3. Import the repository into the [Vercel Dashboard](https://vercel.com).
4. Add your `.env` variables in Vercel.
5. **Note**: For 24/7 data persistence, replace SQLite with a cloud-hosted **PostgreSQL** database (like [Neon.tech](https://neon.tech)).

---

## 📜 License
This project is for educational and emergency response management purposes. 

© 2024 AlertAI Project Team
