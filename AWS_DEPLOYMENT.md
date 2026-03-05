# AWS Deployment Guide – Approved Websites System

This guide covers deploying the **Approved Websites System** to AWS using the updated file structure and execution flow.

➡️ **Back to main documentation:** [README.md](README.md)

---

## ✅ What This Deploys

This AWS deployment hosts:

* `index.html` – the generated approved website directory
* `web_server.py` – the local-style secure HTTP server
* `reports/*.json` – persistent report storage

The system is designed to:

* Run securely on a **single EC2 instance**
* Serve traffic on an **internal network or VPN**
* Avoid cloud dependencies after initial deployment

---

## 📁 Required Project Files on the Server

Your deployed directory should contain:

```
approvedurlpage-henness/
├── build_approved_sites.py        # CSV → HTML generator
├── run_app.py                    # Build + start server launcher
├── web_server.py                 # Secure local HTTP server
├── template.html                 # UI template
├── index.html                    # Generated site directory
├── reports/
│   ├── site_reports.json
│   ├── site_descriptions.json
│   └── category_changes.json
└── SharePoint_List_Export_*.csv   # Optional if building on-server
```

---

## 🖥️ EC2 Instance Requirements

* **AMI**: Ubuntu 22.04 LTS (recommended)
* **Instance Type**: t3.small or higher
* **Storage**: 20–50 GB
* **Security Group**:

  * Allow inbound TCP **8080** (or your chosen port)
  * Optional SSH (22) restricted to admin IPs

---

## 🔧 System Setup

### 1. Install System Packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip git
```

### 2. Upload Project Files

Use **SCP**, **SFTP**, or **Git**:

```bash
git clone <your-repo-url>
cd approvedurlpage-henness
```

---

## 📄 Generating the Website on AWS

If you are generating the site **on the EC2 instance**:

```bash
python3 build_approved_sites.py SharePoint_List_Export_20251208_145101.csv
```

Or to auto-detect the latest CSV:

```bash
python3 run_app.py
```

This will generate:

```
index.html
reports/site_descriptions.json
reports/site_reports.json
reports/category_changes.json
```

---

## 🚀 Running the Server on AWS

### Manual Run

```bash
python3 web_server.py
```

Server will listen at:

```
http://YOUR_EC2_IP:8080
```

---

## ▶️ Production Run Using systemd (Recommended)

Create a service file:

```bash
sudo nano /etc/systemd/system/approved-sites.service
```

Paste:

```ini
[Unit]
Description=Approved Websites Secure Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/approvedurlpage-henness
ExecStart=/usr/bin/python3 web_server.py
Restart=always
RestartSec=10
# Required: set admin password via env (never commit passwords to config)
Environment=ADMIN_PASSWORD=your_secure_password_here

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable approved-sites
sudo systemctl start approved-sites
```

## 📁 **File Structure on AWS Server**
```
/var/www/approved-websites/
├── main.py                    # HTML generator
├── server.py                  # Web server
├── run.py                     # Launch script
├── 20250807_Whitelist_Sites.xlsx  # Excel data
└── approved_websites.html     # Generated HTML

/var/www/reports/
├── site_reports.json          # Main reports file
└── backups/                   # Automatic backups
    ├── reports_backup_20250101_120000.json
    └── reports_backup_20250101_130000.json
```

## 🔒 **Security Configuration**

### 1. **Admin Password**
The admin password is required. Set it via one of these methods:

- **.env file** (recommended): Copy `.env.example` to `.env` and set `ADMIN_PASSWORD=your_secure_password`. The app loads this automatically.
- **systemd**: Add `Environment=ADMIN_PASSWORD=your_secure_password` to the `[Service]` section (as shown above)
- **Manual run**: `ADMIN_PASSWORD=your_secure_password python3 server.py`

### 2. **File Permissions**
```bash
# Set proper permissions
sudo chmod 644 /var/www/approved-websites/*.py
sudo chmod 644 /var/www/approved-websites/*.html
sudo chmod 600 /var/www/reports/site_reports.json
sudo chmod 755 /var/www/reports/backups/
```

### 3. **Firewall Rules**
```bash
# Configure firewall (if using)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### 4. **Access Control**
```bash
# Restrict admin dashboard access
# Add IP restrictions in server.py or use AWS Security Groups
```

## 📊 **Data Management**

### 1. **Backup Strategy**
```bash
scp SharePoint_List_Export_20251208_145101.csv ubuntu@YOUR_EC2_IP:/home/ubuntu/approvedurlpage-henness/
ssh ubuntu@YOUR_EC2_IP
cd approvedurlpage-henness
python3 run_app.py
sudo systemctl restart approved-sites
```

---

## 🔐 Security Recommendations

* Restrict port **8080** to internal IP ranges whenever possible
* Do **not** expose the admin dashboard publicly
* Use VPN or AWS Security Groups for access control
* Regularly back up the `reports/` directory

---

## ✅ Verification Checklist

* [ ] `index.html` loads at `http://EC2_IP:8080`
* [ ] Favorites work and persist across refresh
* [ ] Reports submit successfully
* [ ] `/admin` shows all saved reports
* [ ] `reports/site_reports.json` updates in real time

---

## ✅ Supported Execution Modes

| Mode          | Command                                      |
| ------------- | -------------------------------------------- |
| Build Only    | `python3 build_approved_sites.py export.csv` |
| Build + Serve | `python3 run_app.py`                         |
| Serve Only    | `python3 web_server.py`                      |

---

All file names, commands, and service configuration now match the **current production naming convention**.
