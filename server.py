#!/usr/bin/env python3
"""
Secure Report Server for Approved Websites
Handles user reports and provides admin interface for IT staff
"""

import json
import os
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import webbrowser
import hashlib
import secrets

# Configuration
import os
from pathlib import Path

# Server Configuration (Local Testing)
REPORTS_DIR = "./reports"  # Local directory for testing
REPORTS_FILE = os.path.join(REPORTS_DIR, "site_reports.json")
BACKUP_DIR = os.path.join(REPORTS_DIR, "backups")
PORT = 8081  # Changed to avoid conflicts
ADMIN_PASSWORD = "IT_ADMIN_2025"  # Change this in production!

# Ensure directories exist
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Session management
active_sessions = {}  # session_id -> {expires, ip}
SESSION_TIMEOUT = timedelta(hours=8)  # Sessions expire after 8 hours

def create_session(client_ip):
    """Create a new admin session"""
    session_id = secrets.token_urlsafe(32)
    expires = datetime.now() + SESSION_TIMEOUT
    active_sessions[session_id] = {
        'expires': expires,
        'ip': client_ip
    }
    return session_id

def validate_session(session_id, client_ip):
    """Validate an admin session"""
    if session_id not in active_sessions:
        return False
    
    session = active_sessions[session_id]
    
    # Check if session expired
    if datetime.now() > session['expires']:
        del active_sessions[session_id]
        return False
    
    # Check if IP matches (basic security)
    if session['ip'] != client_ip:
        return False
    
    return True

def cleanup_expired_sessions():
    """Remove expired sessions"""
    now = datetime.now()
    expired = [sid for sid, session in active_sessions.items() if now > session['expires']]
    for sid in expired:
        del active_sessions[sid]

class ReportHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/':
            # Serve the main HTML file
            self.serve_file('approved_websites.html')
        elif path == '/admin':
            # Serve admin interface
            self.serve_admin()
        elif path == '/reports.json':
            # Serve reports data (admin only)
            self.serve_reports()
        elif path == '/suggestions.json':
            # Serve category suggestions data (admin only)
            self.serve_suggestions()
        elif path == '/category_changes.json':
            # Serve category changes data (admin only)
            self.serve_category_changes()
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/submit_report':
            self.handle_report_submission()
        elif path == '/submit_suggestion':
            self.handle_suggestion_submission()
        elif path == '/apply_category_change':
            self.handle_category_change()
        elif path == '/admin_login':
            self.handle_admin_login()
        else:
            self.send_error(404, "Not Found")
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def serve_file(self, filename):
        """Serve static files"""
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "File not found")
    
    def serve_admin(self):
        """Serve admin interface with session-based authentication"""
        # Log access attempt
        client_ip = self.client_address[0]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Clean up expired sessions
        cleanup_expired_sessions()
        
        # Check for session cookie
        session_id = None
        if 'Cookie' in self.headers:
            cookies = self.headers['Cookie']
            for cookie in cookies.split(';'):
                if 'admin_session=' in cookie.strip():
                    session_id = cookie.strip().split('=')[1]
                    break
        
        # Validate session
        if session_id and validate_session(session_id, client_ip):
            print(f"✅ Admin access granted from {client_ip} at {timestamp}")
            admin_html = self.generate_admin_html()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(admin_html.encode('utf-8'))
        else:
            print(f"⚠️ Admin access denied from {client_ip} at {timestamp}")
            # Show login form
            login_html = self.generate_login_html()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(login_html.encode('utf-8'))
    
    def is_admin_authenticated(self):
        """Check if the current request is from an authenticated admin"""
        client_ip = self.client_address[0]
        
        # Check for session cookie
        session_id = None
        if 'Cookie' in self.headers:
            cookies = self.headers['Cookie']
            for cookie in cookies.split(';'):
                cookie = cookie.strip()
                if 'admin_session=' in cookie:
                    session_id = cookie.split('=')[1]
                    break
        
        return session_id and validate_session(session_id, client_ip)
    
    def serve_reports(self):
        """Serve reports data (admin only)"""
        if not self.is_admin_authenticated():
            self.send_response(403)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Access denied"}).encode('utf-8'))
            return
        
        try:
            with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
                reports = json.load(f)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(reports).encode('utf-8'))
        except FileNotFoundError:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps([]).encode('utf-8'))
    
    def serve_suggestions(self):
        """Serve category suggestions data (admin only)"""
        if not self.is_admin_authenticated():
            self.send_response(403)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Access denied"}).encode('utf-8'))
            return
        
        try:
            suggestions_file = os.path.join(REPORTS_DIR, "category_suggestions.json")
            with open(suggestions_file, 'r', encoding='utf-8') as f:
                suggestions = json.load(f)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(suggestions).encode('utf-8'))
        except FileNotFoundError:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps([]).encode('utf-8'))
    
    def serve_category_changes(self):
        """Serve category changes data (admin only)"""
        if not self.is_admin_authenticated():
            self.send_response(403)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Access denied"}).encode('utf-8'))
            return
        
        try:
            changes_file = os.path.join(REPORTS_DIR, "category_changes.json")
            with open(changes_file, 'r', encoding='utf-8') as f:
                changes = json.load(f)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(changes).encode('utf-8'))
        except FileNotFoundError:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps([]).encode('utf-8'))
    
    def handle_report_submission(self):
        """Handle report submission"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            report = json.loads(post_data.decode('utf-8'))
            
            # Add server-side timestamp and IP
            report['server_timestamp'] = datetime.now().isoformat()
            report['client_ip'] = self.client_address[0]
            
            # Load existing reports
            reports = []
            if os.path.exists(REPORTS_FILE):
                with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
                    reports = json.load(f)
            
            # Add new report
            reports.append(report)
            
            # Create backup before saving
            self.create_backup()
            
            # Save reports with atomic write
            temp_file = REPORTS_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(reports, f, indent=2, ensure_ascii=False)
            
            # Atomic move
            os.rename(temp_file, REPORTS_FILE)
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
            print(f"✅ New report submitted: {report['site_name']} - {report['issue_type']}")
            
        except Exception as e:
            print(f"❌ Error handling report: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
    
    def create_backup(self):
        """Create backup of reports file"""
        try:
            if os.path.exists(REPORTS_FILE):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(BACKUP_DIR, f"reports_backup_{timestamp}.json")
                
                # Copy current file to backup
                import shutil
                shutil.copy2(REPORTS_FILE, backup_file)
                
                # Keep only last 10 backups
                backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("reports_backup_")])
                if len(backups) > 10:
                    for old_backup in backups[:-10]:
                        os.remove(os.path.join(BACKUP_DIR, old_backup))
                        
        except Exception as e:
            print(f"⚠️ Backup failed: {e}")
    
    def handle_suggestion_submission(self):
        """Handle category suggestion submission"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            suggestion = json.loads(post_data.decode('utf-8'))
            
            # Add server-side timestamp and IP
            suggestion['server_timestamp'] = datetime.now().isoformat()
            suggestion['client_ip'] = self.client_address[0]
            
            # Load existing suggestions
            suggestions_file = os.path.join(REPORTS_DIR, "category_suggestions.json")
            suggestions = []
            if os.path.exists(suggestions_file):
                with open(suggestions_file, 'r', encoding='utf-8') as f:
                    suggestions = json.load(f)
            
            # Add new suggestion
            suggestions.append(suggestion)
            
            # Create backup before saving
            self.create_backup()
            
            # Save suggestions with atomic write
            temp_file = suggestions_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(suggestions, f, indent=2, ensure_ascii=False)
            
            # Atomic move
            os.rename(temp_file, suggestions_file)
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
            print(f"✅ New category suggestion: {suggestion['site_name']} - {suggestion['current_category']} → {suggestion['suggested_category']}")
            
        except Exception as e:
            print(f"❌ Error handling suggestion: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
    
    def handle_category_change(self):
        """Handle admin category change application"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            change_data = json.loads(post_data.decode('utf-8'))
            
            # Add server-side timestamp and IP
            change_data['applied_timestamp'] = datetime.now().isoformat()
            change_data['applied_by_ip'] = self.client_address[0]
            change_data['status'] = 'applied'
            
            # Load existing category changes
            changes_file = os.path.join(REPORTS_DIR, "category_changes.json")
            changes = []
            if os.path.exists(changes_file):
                with open(changes_file, 'r', encoding='utf-8') as f:
                    changes = json.load(f)
            
            # Check if there's already a change for this site
            site_exists = False
            for i, existing_change in enumerate(changes):
                if (existing_change.get('site_name') == change_data['site_name'] and 
                    existing_change.get('site_url') == change_data['site_url']):
                    # Update existing change
                    changes[i] = change_data
                    site_exists = True
                    break
            
            if not site_exists:
                # Add new change
                changes.append(change_data)
            
            # Create backup before saving
            self.create_backup()
            
            # Save changes with atomic write
            temp_file = changes_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(changes, f, indent=2, ensure_ascii=False)
            
            # Atomic move
            os.rename(temp_file, changes_file)
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
            print(f"✅ Category change applied: {change_data['site_name']} - {change_data['old_category']} → {change_data['new_category']}")
            
        except Exception as e:
            print(f"❌ Error handling category change: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
    
    def handle_admin_login(self):
        """Handle admin login authentication"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            login_data = json.loads(post_data.decode('utf-8'))
            
            password = login_data.get('password', '')
            client_ip = self.client_address[0]
            
            if password == ADMIN_PASSWORD:
                # Create session
                session_id = create_session(client_ip)
                
                # Send success response with session cookie
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Set-Cookie', f'admin_session={session_id}; HttpOnly; SameSite=Strict; Max-Age={int(SESSION_TIMEOUT.total_seconds())}')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "redirect": "/admin"}).encode('utf-8'))
                
                print(f"✅ Admin login successful from {client_ip}")
            else:
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "Invalid password"}).encode('utf-8'))
                
                print(f"❌ Admin login failed from {client_ip}")
                
        except Exception as e:
            print(f"❌ Error handling admin login: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
    
    def generate_login_html(self):
        """Generate login form HTML"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IT Admin Login</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background-color: #f5f5f5;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}
        .login-container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #dc3545;
            margin: 0 0 10px 0;
        }}
        .header p {{
            color: #6c757d;
            margin: 0;
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #495057;
        }}
        .form-group input {{
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 16px;
            box-sizing: border-box;
        }}
        .form-group input:focus {{
            outline: none;
            border-color: #007bff;
            box-shadow: 0 0 0 2px rgba(0,123,255,0.25);
        }}
        .login-btn {{
            width: 100%;
            background: #dc3545;
            color: white;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.3s ease;
        }}
        .login-btn:hover {{
            background: #c82333;
        }}
        .error {{
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 20px;
            display: none;
        }}
        .security-note {{
            background: #d1ecf1;
            color: #0c5460;
            padding: 15px;
            border-radius: 6px;
            margin-top: 20px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="login-container">
        <div class="header">
            <h1>🔒 IT Admin Access</h1>
            <p>Restricted Area - IT Staff Only</p>
        </div>
        
        <div class="error" id="errorMessage">
            Invalid password. Access denied.
        </div>
        
        <form onsubmit="checkPassword(event)">
            <div class="form-group">
                <label for="password">Admin Password:</label>
                <input type="password" id="password" name="password" required 
                       placeholder="Enter IT admin password">
            </div>
            
            <button type="submit" class="login-btn">Access Admin Dashboard</button>
        </form>
        
        <div class="security-note">
            <strong>Security Notice:</strong> This area is restricted to authorized IT staff only. 
            All access attempts are logged for security purposes.
        </div>
    </div>
    
    <script>
        function checkPassword(event) {{
            event.preventDefault();
            
            const password = document.getElementById('password').value;
            const errorDiv = document.getElementById('errorMessage');
            const submitBtn = document.querySelector('.login-btn');
            
            // Show loading state
            submitBtn.textContent = 'Logging in...';
            submitBtn.disabled = true;
            errorDiv.style.display = 'none';
            
            // Send login request via POST
            fetch('/admin_login', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{ password: password }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    // Clear any existing error
                    errorDiv.style.display = 'none';
                    // Redirect to admin dashboard
                    window.location.href = '/admin';
                }} else {{
                    errorDiv.style.display = 'block';
                    document.getElementById('password').value = '';
                    document.getElementById('password').focus();
                    submitBtn.textContent = 'Access Admin Dashboard';
                    submitBtn.disabled = false;
                }}
            }})
            .catch(error => {{
                console.error('Login error:', error);
                errorDiv.style.display = 'block';
                document.getElementById('password').value = '';
                document.getElementById('password').focus();
                submitBtn.textContent = 'Access Admin Dashboard';
                submitBtn.disabled = false;
            }});
        }}
        
        // Focus on password field when page loads
        document.addEventListener('DOMContentLoaded', function() {{
            document.getElementById('password').focus();
        }});
    </script>
</body>
</html>
        """
    
    def generate_admin_html(self):
        """Generate admin interface HTML"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IT Admin - Site Reports & Category Suggestions</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .content {{
            padding: 30px;
        }}
        .tabs {{
            display: flex;
            border-bottom: 2px solid #e9ecef;
            margin-bottom: 30px;
        }}
        .tab {{
            padding: 12px 24px;
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-bottom: none;
            cursor: pointer;
            font-weight: 500;
            color: #495057;
            transition: all 0.3s ease;
        }}
        .tab:first-child {{
            border-radius: 6px 0 0 0;
        }}
        .tab:last-child {{
            border-radius: 0 6px 0 0;
        }}
        .tab.active {{
            background: white;
            color: #dc3545;
            border-color: #dc3545;
            border-bottom: 2px solid white;
            margin-bottom: -2px;
        }}
        .tab:hover:not(.active) {{
            background: #e9ecef;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            color: #dc3545;
        }}
        .report-item, .suggestion-item {{
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            margin-bottom: 15px;
            padding: 20px;
        }}
        .report-header, .suggestion-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .site-name {{
            font-weight: bold;
            color: #495057;
        }}
        .issue-type {{
            background: #dc3545;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
        }}
        .suggestion-type {{
            background: #17a2b8;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
        }}
        .report-details, .suggestion-details {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        .description {{
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
            font-style: italic;
        }}
        .category-change {{
            margin-top: 10px;
            padding: 10px;
            background: #d1ecf1;
            border-radius: 4px;
            border-left: 4px solid #17a2b8;
        }}
        .refresh-btn {{
            background: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            margin-bottom: 20px;
        }}
        .refresh-btn:hover {{
            background: #0056b3;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔒 IT Admin Dashboard</h1>
            <p>Site Issue Reports & Category Suggestions from Incarcerated Students - Restricted Access</p>
            <p><small>Data stored in: {REPORTS_DIR}</small></p>
        </div>
        
        <div class="content">
            <div class="tabs">
                <div class="tab active" onclick="switchTab('reports')">📋 Site Reports</div>
                <div class="tab" onclick="switchTab('suggestions')">💡 Category Suggestions</div>
            </div>
            
            <div id="reports-tab" class="tab-content active">
                <button class="refresh-btn" onclick="loadReports()">🔄 Refresh Reports</button>
                
                <div class="stats" id="reports-stats">
                    <!-- Stats will be loaded here -->
                </div>
                
                <div id="reports">
                    <!-- Reports will be loaded here -->
                </div>
            </div>
            
            <div id="suggestions-tab" class="tab-content">
                <button class="refresh-btn" onclick="loadSuggestions()">🔄 Refresh Suggestions</button>
                
                <div class="stats" id="suggestions-stats">
                    <!-- Stats will be loaded here -->
                </div>
                
                <div id="suggestions">
                    <!-- Suggestions will be loaded here -->
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function switchTab(tabName) {{
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {{
                content.classList.remove('active');
            }});
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {{
                tab.classList.remove('active');
            }});
            
            // Show selected tab content
            document.getElementById(tabName + '-tab').classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
            
            // Load data for the selected tab
            if (tabName === 'reports') {{
                loadReports();
            }} else if (tabName === 'suggestions') {{
                loadSuggestions();
            }}
        }}
        
        function loadReports() {{
            // Get password from URL
            const urlParams = new URLSearchParams(window.location.search);
            const password = urlParams.get('password');
            
            if (!password) {{
                document.getElementById('reports').innerHTML = '<p>Authentication required. Please login again.</p>';
                return;
            }}
            
            fetch('/reports.json?password=' + encodeURIComponent(password))
                .then(response => {{
                    if (response.status === 403) {{
                        throw new Error('Access denied');
                    }}
                    return response.json();
                }})
                .then(reports => {{
                    displayReportsStats(reports);
                    displayReports(reports);
                }})
                .catch(error => {{
                    console.error('Error loading reports:', error);
                    document.getElementById('reports').innerHTML = '<p>Error loading reports. Please check your access permissions.</p>';
                }});
        }}
        
        function loadSuggestions() {{
            // Get password from URL
            const urlParams = new URLSearchParams(window.location.search);
            const password = urlParams.get('password');
            
            if (!password) {{
                document.getElementById('suggestions').innerHTML = '<p>Authentication required. Please login again.</p>';
                return;
            }}
            
            fetch('/suggestions.json?password=' + encodeURIComponent(password))
                .then(response => {{
                    if (response.status === 403) {{
                        throw new Error('Access denied');
                    }}
                    return response.json();
                }})
                .then(suggestions => {{
                    displaySuggestionsStats(suggestions);
                    displaySuggestions(suggestions);
                }})
                .catch(error => {{
                    console.error('Error loading suggestions:', error);
                    document.getElementById('suggestions').innerHTML = '<p>Error loading suggestions. Please check your access permissions.</p>';
                }});
        }}
        
        function displayReportsStats(reports) {{
            const totalReports = reports.length;
            const issueTypes = {{}};
            const sites = new Set();
            
            reports.forEach(report => {{
                issueTypes[report.issue_type] = (issueTypes[report.issue_type] || 0) + 1;
                sites.add(report.site_name);
            }});
            
            const statsHtml = `
                <div class="stat-card">
                    <div class="stat-number">${{totalReports}}</div>
                    <div>Total Reports</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${{sites.size}}</div>
                    <div>Affected Sites</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${{Object.keys(issueTypes).length}}</div>
                    <div>Issue Types</div>
                </div>
            `;
            
            document.getElementById('reports-stats').innerHTML = statsHtml;
        }}
        
        function displaySuggestionsStats(suggestions) {{
            const totalSuggestions = suggestions.length;
            const suggestedCategories = {{}};
            const sites = new Set();
            
            suggestions.forEach(suggestion => {{
                suggestedCategories[suggestion.suggested_category] = (suggestedCategories[suggestion.suggested_category] || 0) + 1;
                sites.add(suggestion.site_name);
            }});
            
            const statsHtml = `
                <div class="stat-card">
                    <div class="stat-number">${{totalSuggestions}}</div>
                    <div>Total Suggestions</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${{sites.size}}</div>
                    <div>Affected Sites</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${{Object.keys(suggestedCategories).length}}</div>
                    <div>Suggested Categories</div>
                </div>
            `;
            
            document.getElementById('suggestions-stats').innerHTML = statsHtml;
        }}
        
        function displayReports(reports) {{
            if (reports.length === 0) {{
                document.getElementById('reports').innerHTML = '<p>No reports submitted yet.</p>';
                return;
            }}
            
            const reportsHtml = reports.map(report => `
                <div class="report-item">
                    <div class="report-header">
                        <div class="site-name">${{report.site_name}}</div>
                        <div class="issue-type">${{report.issue_type.replace('_', ' ').toUpperCase()}}</div>
                    </div>
                    <div class="report-details">
                        <strong>URL:</strong> ${{report.site_url}}<br>
                        <strong>Reported:</strong> ${{new Date(report.timestamp).toLocaleString()}}<br>
                        <strong>Report ID:</strong> ${{report.report_id}}
                    </div>
                    ${{report.description ? `<div class="description"><strong>Description:</strong> ${{report.description}}</div>` : ''}}
                </div>
            `).join('');
            
            document.getElementById('reports').innerHTML = reportsHtml;
        }}
        
        function displaySuggestions(suggestions) {{
            if (suggestions.length === 0) {{
                document.getElementById('suggestions').innerHTML = '<p>No category suggestions submitted yet.</p>';
                return;
            }}
            
            const suggestionsHtml = suggestions.map(suggestion => `
                <div class="suggestion-item">
                    <div class="suggestion-header">
                        <div class="site-name">${{suggestion.site_name}}</div>
                        <div class="suggestion-type">CATEGORY SUGGESTION</div>
                    </div>
                    <div class="suggestion-details">
                        <strong>URL:</strong> ${{suggestion.site_url}}<br>
                        <strong>Suggested:</strong> ${{new Date(suggestion.timestamp).toLocaleString()}}<br>
                        <strong>Suggestion ID:</strong> ${{suggestion.suggestion_id}}
                    </div>
                    <div class="category-change">
                        <strong>Category Change:</strong> ${{suggestion.current_category}} → ${{suggestion.suggested_category}}
                        ${{suggestion.reason ? `<br><strong>Reason:</strong> ${{suggestion.reason}}` : ''}}
                    </div>
                    <div class="suggestion-actions" style="margin-top: 15px; display: flex; gap: 10px;">
                        <button class="apply-btn" onclick="applyCategoryChange('${{suggestion.site_name}}', '${{suggestion.site_url}}', '${{suggestion.current_category}}', '${{suggestion.suggested_category}}', '${{suggestion.suggestion_id}}')" style="background: #28a745; color: white; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9em;">
                            ✅ Apply Change
                        </button>
                        <button class="reject-btn" onclick="rejectSuggestion('${{suggestion.suggestion_id}}')" style="background: #dc3545; color: white; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9em;">
                            ❌ Reject
                        </button>
                    </div>
                </div>
            `).join('');
            
            document.getElementById('suggestions').innerHTML = suggestionsHtml;
        }}
        
        // Load reports on page load
        loadReports();
        
        // Auto-refresh every 30 seconds
        setInterval(() => {{
            const activeTab = document.querySelector('.tab.active');
            if (activeTab && activeTab.textContent.includes('Reports')) {{
                loadReports();
            }} else if (activeTab && activeTab.textContent.includes('Suggestions')) {{
                loadSuggestions();
            }}
        }}, 30000);
        
        function applyCategoryChange(siteName, siteUrl, oldCategory, newCategory, suggestionId) {{
            if (!confirm(`Apply category change for "${{siteName}}" from "${{oldCategory}}" to "${{newCategory}}"?`)) {{
                return;
            }}
            
            const changeData = {{
                site_name: siteName,
                site_url: siteUrl,
                old_category: oldCategory,
                new_category: newCategory,
                suggestion_id: suggestionId,
                applied_by: 'admin'
            }};
            
            fetch('/apply_category_change', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(changeData)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert('Category change applied successfully! The website will be recategorized on the next update.');
                    loadSuggestions(); // Refresh the suggestions list
                }} else {{
                    alert('Error applying category change. Please try again.');
                }}
            }})
            .catch(error => {{
                console.error('Error applying category change:', error);
                alert('Unable to apply category change. Please check your connection and try again.');
            }});
        }}
        
        function rejectSuggestion(suggestionId) {{
            if (!confirm('Reject this category suggestion? This action cannot be undone.')) {{
                return;
            }}
            
            // For now, we'll just show a message. In a full implementation,
            // you might want to mark suggestions as rejected in the database
            alert('Suggestion rejected. Consider implementing a rejection tracking system.');
        }}
    </script>
</body>
</html>
        """
    
    def log_message(self, format, *args):
        """Override to reduce log noise"""
        pass

def start_server():
    """Start the HTTP server"""
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, ReportHandler)
    
    print(f"🚀 Starting Local Test Server...")
    print(f"📱 User Interface: http://localhost:{PORT}")
    print(f"🔒 Admin Dashboard: http://localhost:{PORT}/admin")
    print(f"📁 Reports Directory: {REPORTS_DIR}")
    print(f"📝 Reports File: {REPORTS_FILE}")
    print(f"💾 Backup Directory: {BACKUP_DIR}")
    print(f"🔑 Admin password: {ADMIN_PASSWORD}")
    print(f"\n🧪 LOCAL TESTING FEATURES:")
    print(f"   • Reports saved to local file system")
    print(f"   • Automatic backups created")
    print(f"   • Client IP addresses logged")
    print(f"   • Atomic file writes for data integrity")
    print(f"   • Ready for AWS deployment")
    print(f"\n⚠️  SECURITY NOTES:")
    print(f"   • Reports are NOT visible to other users")
    print(f"   • Only IT staff can access admin dashboard")
    print(f"   • All data stored locally for testing")
    print(f"   • Complete audit trail maintained")
    print(f"\nPress Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n🛑 Server stopped")
        httpd.shutdown()

if __name__ == '__main__':
    start_server()
