# Approved Websites System - Prison Environment

## 🔒 Security Features

This system is designed specifically for prison environments with strict security requirements:

### ✅ **User Privacy Protected**
- **Reports are NOT visible to other incarcerated students**
- **No user-to-user communication**
- **No shared comment system**
- **Each user's reports are private**

### ✅ **IT Staff Access Only**
- **Admin dashboard accessible only to IT staff**
- **All reports stored securely on local server**
- **No external network dependencies**
- **Complete audit trail of all reports**

### ✅ **Local Data Storage**
- **All data stays on local server**
- **No cloud services or external APIs**
- **Reports stored in encrypted JSON format**
- **Backup and export capabilities**

## 🚀 Quick Start

### 1. Generate Website Listing
```bash
python main.py
```

### 2. Start Secure Server
```bash
python server.py
```

### 3. Access Interfaces
- **User Interface**: http://localhost:8080
- **IT Admin Dashboard**: http://localhost:8080/admin

## 📱 User Interface Features

### For Incarcerated Students:
- Browse approved websites by category
- Search for specific sites
- Report issues with websites
- Clean, simple interface
- No access to other users' reports

### Report Types Available:
- Site not loading
- Site blocked/filtered
- Content issues
- Slow loading
- Broken links
- Other technical problems

## 🔒 IT Admin Dashboard

### Features:
- View all submitted reports
- Filter by issue type
- See affected sites
- Export reports for analysis
- Real-time updates
- Complete audit trail

### Security:
- Password protected access
- Local server only
- No external dependencies
- Complete data control

## 📊 Data Management

### Report Storage:
- **File**: `site_reports.json`
- **Format**: JSON with timestamps
- **Backup**: Manual export available
- **Privacy**: No user identification stored

### Report Structure:
```json
{
  "site_name": "Example Site",
  "site_url": "https://example.com",
  "issue_type": "site_not_loading",
  "description": "User description",
  "timestamp": "2025-01-XX...",
  "report_id": "unique_id"
}
```

## 🛡️ Security Considerations

### For Prison Environment:
1. **No User Identification**: Reports don't identify specific users
2. **Local Storage Only**: All data stays on local server
3. **IT Control**: Only IT staff can access reports
4. **No External Access**: System works offline
5. **Audit Trail**: Complete logging of all activities

### Deployment Recommendations:
1. **Dedicated Server**: Run on prison IT network only
2. **Access Control**: Restrict admin dashboard access
3. **Regular Backups**: Export reports regularly
4. **Monitoring**: Monitor server logs for issues
5. **Updates**: Keep system updated for security

## 🔧 Technical Details

### Requirements:
- Python 3.7+
- pandas
- openpyxl
- Standard library modules

### Files:
- `main.py` - Generates HTML from Excel
- `server.py` - Secure HTTP server
- `run.py` - Launch script
- `site_reports.json` - Report storage
- `approved_websites.html` - User interface

### Port Configuration:
- Default: Port 8080
- Change in `server.py` if needed
- Ensure port is available

## 📋 Usage Instructions

### For IT Staff:
1. Run `python run.py` to start system
2. Access admin dashboard at `/admin`
3. Monitor reports regularly
4. Export data for analysis
5. Update website list as needed

### For Users:
1. Open browser to local server
2. Browse websites by category
3. Click "Report Issue" for problems
4. Fill out simple form
5. Submit report (goes to IT only)

## ⚠️ Important Notes

- **Reports are private** - users cannot see other users' reports
- **IT access only** - admin dashboard is restricted
- **Local data** - no external services used
- **Secure by design** - built for prison environment
- **Audit ready** - complete logging and tracking

## 🔄 Updates and Maintenance

### Regular Tasks:
1. **Monitor reports** - Check admin dashboard daily
2. **Export data** - Backup reports regularly
3. **Update sites** - Refresh Excel file as needed
4. **System updates** - Keep Python and dependencies current
5. **Security review** - Regular security assessments

### Troubleshooting:
- Check server logs for errors
- Verify file permissions
- Ensure port availability
- Test report submission
- Validate admin access

---

**Built for secure prison environments with privacy and security as top priorities.**





