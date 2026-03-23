// Main JavaScript for Emergency Response System

class EmergencySystem {
    constructor() {
        this.socket = null;
        this.currentLocation = null;
        this.map = null;
        this.markers = {};
        this.initialize();
    }

    initialize() {
        this.initializeSocket();
        this.setupEventListeners();
        this.getCurrentLocation();
        this.checkForNotifications();
    }

    initializeSocket() {
        this.socket = io();

        this.socket.on('connect', () => {
            console.log('Connected to server');
        });

        this.socket.on('new_incident', (data) => {
            this.showNotification('New incident reported!', 'info');
            if (this.map) {
                this.addIncidentMarker(data);
            }
        });

        this.socket.on('incident_update', (data) => {
            this.showNotification('Incident status updated', 'info');
            this.updateIncidentMarker(data);
        });

        this.socket.on('assignment', (data) => {
            if (data.assignee_type === 'user' && data.user_id === window.userId) {
                this.showEmergencyAssignment(data);
            }
        });
    }

    getCurrentLocation() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    this.currentLocation = {
                        lat: position.coords.latitude,
                        lng: position.coords.longitude
                    };
                    localStorage.setItem('lastLocation', JSON.stringify(this.currentLocation));
                },
                (error) => {
                    console.error('Geolocation error:', error);
                    // Use default location (New Delhi)
                    this.currentLocation = { lat: 28.6139, lng: 77.2090 };
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        } else {
            this.currentLocation = { lat: 28.6139, lng: 77.2090 };
        }
    }

    setupEventListeners() {
        // Emergency button
        const emergencyBtn = document.getElementById('emergencyBtn');
        if (emergencyBtn) {
            emergencyBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.reportEmergency();
            });
        }

        // Location sharing toggle
        const locationToggle = document.getElementById('locationToggle');
        if (locationToggle) {
            locationToggle.addEventListener('change', (e) => {
                this.toggleLocationSharing(e.target.checked);
            });
        }

        // Initialize tooltips
        const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltips.forEach(tooltip => {
            new bootstrap.Tooltip(tooltip);
        });
    }

    showNotification(message, type = 'info') {
        // Check if browser supports notifications
        if ("Notification" in window && Notification.permission === "granted") {
            new Notification("Emergency System", {
                body: message,
                icon: "/static/images/icon-192.png"
            });
        }

        // Show in-app notification
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = `
            top: 70px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
        `;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(alertDiv);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }

    async reportEmergency() {
        if (!this.currentLocation) {
            this.showNotification('Getting your location...', 'warning');
            // Try to wait a bit for location
            let attempts = 0;
            while (!this.currentLocation && attempts < 3) {
                await new Promise(resolve => setTimeout(resolve, 1000));
                attempts++;
            }
        }

        window.location.href = '/emergency/report';
    }

    async toggleLocationSharing(enabled) {
        if (enabled && !this.currentLocation) {
            this.getCurrentLocation();
        }

        // Send to server
        try {
            const response = await fetch('/api/update_location', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    is_sharing: enabled,
                    latitude: this.currentLocation ? this.currentLocation.lat : null,
                    longitude: this.currentLocation ? this.currentLocation.lng : null
                })
            });

            const data = await response.json();
            if (data.success) {
                this.showNotification('Location sharing ' + (enabled ? 'enabled' : 'disabled'), 'success');
            }
        } catch (error) {
            console.error('Error updating location:', error);
        }
    }

    showEmergencyAssignment(data) {
        const modalElement = document.getElementById('assignmentModal');
        if (!modalElement) return;

        const modal = new bootstrap.Modal(modalElement);
        const modalContent = document.getElementById('assignmentContent');

        if (modalContent) {
            modalContent.innerHTML = `
                <div class="alert alert-danger">
                    <h4><i class="fas fa-bell"></i> Emergency Assistance Requested</h4>
                    <p><strong>Incident:</strong> ${data.emergency_type || 'Unknown'}</p>
                    <p><strong>Location:</strong> ${data.distance ? `${data.distance.toFixed(1)}km away` : 'Nearby'}</p>
                    <p><strong>Severity:</strong> ${data.severity || 'Medium'}</p>
                    <p>Can you help with this emergency?</p>
                </div>
                <div class="text-center">
                    <button class="btn btn-success btn-lg me-2" onclick="acceptAssignment(${data.incident_id})">
                        <i class="fas fa-check"></i> Accept
                    </button>
                    <button class="btn btn-secondary btn-lg" data-bs-dismiss="modal">
                        <i class="fas fa-times"></i> Decline
                    </button>
                </div>
            `;
            modal.show();
        }
    }

    checkForNotifications() {
        // Only check if user is logged in
        if (!window.userId) return;

        // Check for new notifications every 30 seconds
        setInterval(async () => {
            try {
                const response = await fetch('/api/notifications');
                if (response.ok) {
                    const data = await response.json();
                    if (data.notifications && data.notifications.length > 0) {
                        data.notifications.forEach(notification => {
                            this.showNotification(notification.message);
                        });
                    }
                }
            } catch (error) {
                console.error('Error checking notifications:', error);
            }
        }, 30000);
    }

    // Map methods
    initializeMap(elementId, center = null, zoom = 13) {
        const mapElement = document.getElementById(elementId);
        if (!mapElement) return null;

        if (!center) {
            center = this.currentLocation ? [this.currentLocation.lat, this.currentLocation.lng] : [28.6139, 77.2090];
        }

        try {
            this.map = L.map(elementId).setView(center, zoom);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(this.map);

            return this.map;
        } catch (e) {
            console.error('Error initializing Leaflet map:', e);
            mapElement.innerHTML = `<div class="alert alert-danger">Failed to load map: ${e.message}</div>`;
            return null;
        }
    }

    addIncidentMarker(data) {
        const [lat, lng] = data.location.split(',').map(Number);
        const icon = this.getIncidentIcon(data.severity);

        const marker = L.marker([lat, lng], { icon: icon })
            .addTo(this.map)
            .bindPopup(`
                <strong>${data.type}</strong><br>
                Severity: ${data.severity}<br>
                <a href="/admin/incident/${data.id}" target="_blank">View Details</a>
            `);

        this.markers[`incident_${data.id}`] = marker;
        return marker;
    }

    getIncidentIcon(severity) {
        const colors = {
            critical: 'red',
            high: 'orange',
            medium: 'yellow',
            low: 'green'
        };

        return L.divIcon({
            className: 'incident-marker',
            html: `<div class="marker-pin" style="background-color: ${colors[severity] || 'gray'}"></div>`,
            iconSize: [30, 42],
            iconAnchor: [15, 42]
        });
    }
}

// Initialize system when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    window.emergencySystem = new EmergencySystem();

    // Global functions
    window.acceptAssignment = async function (incidentId) {
        try {
            const response = await fetch(`/api/assignment/${incidentId}/accept`, {
                method: 'POST'
            });

            const data = await response.json();
            if (data.success) {
                emergencySystem.showNotification('Assignment accepted!');
                bootstrap.Modal.getInstance(document.getElementById('assignmentModal')).hide();

                // Redirect to tracking page
                window.location.href = `/tracking/${incidentId}`;
            }
        } catch (error) {
            console.error('Error accepting assignment:', error);
            emergencySystem.showNotification('Error accepting assignment', 'danger');
        }
    };

    // Request notification permission
    if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
    }

    // Register service worker for PWA
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(reg => console.log('Service Worker registered'))
            .catch(err => console.log('Service Worker registration failed:', err));
    }
});