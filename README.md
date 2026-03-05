# Approved Websites System – Prison Environment

> ⚠️ **Security-First, Offline-Capable Website Directory for Corrections Education**

This system generates and serves a secure, categorized directory of **approved websites** for incarcerated students. It is designed to operate entirely on a **local network**, with **no cloud dependencies**, while providing IT staff with a private administrative reporting interface.

---

## 🔗 Deployment Guide

For AWS and server deployment instructions, see:

➡️ **[AWS Deployment Guide](AWS_DEPLOYMENT.md)**

---

## ✅ Key Security Features

- **User privacy protected** – reports are never visible to other users
- **IT staff access only** – admin dashboard is restricted
- **No external services required** – fully offline capable
- **Local JSON storage** with controlled access
- **Auditable report trail** with timestamps

---

## 🚀 Quick Start (Local)

### 0. Configure Admin Password (required for server)
Copy `.env.example` to `.env` and set your admin dashboard password. The server will not start without this.

### 1. Generate Website Listing

```bash
python build_approved_sites.py SharePoint_List_Export_20251208_145101.csv
```

Or auto-detect the latest export:

```bash
python run_app.py
```

### 2. Start Secure Server

```bash
python web_server.py
```

Or launch everything together:

```bash
python run_app.py
```

### 3. Access Interfaces

- **User Interface**: `http://localhost:8080`
- **IT Admin Dashboard**: `http://localhost:8080/admin`

---

## 📁 Current File Structure

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
└── SharePoint_List_Export_*.csv
```

---

## 📱 User Interface Features

### For Incarcerated Students

- Browse approved websites by category
- Favorites with drag-and-drop ordering
- Report issues with websites
- Clean, simplified interface
- No user tracking or cross-user visibility

### Report Types Available

- Site not loading
- Site blocked or filtered
- Broken links
- Slow loading
- Content issues
- Other technical problems

---

## 🔒 IT Admin Dashboard

### Features

- View all submitted reports
- Filter by issue type and site
- Export reports
- Full timestamped audit trail

### Security

- Password protected
- Local server only
- No external authentication
- No user identity stored

---

## 📊 Report Data

### Storage

- **File**: `reports/site_reports.json`
- **Format**: JSON
- **Backups**: Manual or scheduled

### Example Report

```json
{
  "site_name": "Example Site",
  "site_url": "https://example.com",
  "issue_type": "site_not_loading",
  "description": "User description",
  "timestamp": "2025-01-01T12:00:00",
  "report_id": "unique_id"
}
```

---

## 🛡️ Prison Environment Design Goals

- No user identity tracking
- No peer-to-peer communication
- No shared report visibility
- Fully offline capable
- IT-controlled updates and exports

---

## 🔄 Maintenance Workflow

1. Upload new SharePoint CSV
2. Run `python run_app.py`
3. Review reports via `/admin`
4. Export backups as needed

---

## ✅ Recommended Execution Flow

- **Daily use**: `python web_server.py`
- **When CSV updates**: `python run_app.py`

---

**Built for secure corrections education environments with privacy and operational integrity as top priorities.**

