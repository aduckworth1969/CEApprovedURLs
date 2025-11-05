# AWS Deployment Guide - Approved Websites System

## ☁️ AWS Server Setup

### 1. **EC2 Instance Configuration**
```bash
# Recommended instance type
t3.small or t3.medium (depending on user load)

# Operating System
Amazon Linux 2 or Ubuntu 20.04 LTS

# Security Group Rules
- Port 80 (HTTP) - Open to prison network only
- Port 443 (HTTPS) - Optional, for SSL
- Port 22 (SSH) - IT staff access only
```

### 2. **Server Setup Commands**
```bash
# Update system
sudo yum update -y  # Amazon Linux
# or
sudo apt update && sudo apt upgrade -y  # Ubuntu

# Install Python 3
sudo yum install python3 python3-pip -y  # Amazon Linux
# or
sudo apt install python3 python3-pip -y  # Ubuntu

# Install required packages
pip3 install pandas openpyxl

# Create application directory
sudo mkdir -p /var/www/approved-websites
sudo chown ec2-user:ec2-user /var/www/approved-websites

# Create reports directory
sudo mkdir -p /var/www/reports
sudo chown ec2-user:ec2-user /var/www/reports
sudo chmod 755 /var/www/reports
```

### 3. **File Upload**
```bash
# Upload files to server
scp -i your-key.pem main.py ec2-user@your-server:/var/www/approved-websites/
scp -i your-key.pem server.py ec2-user@your-server:/var/www/approved-websites/
scp -i your-key.pem run.py ec2-user@your-server:/var/www/approved-websites/
scp -i your-key.pem 20250807_Whitelist_Sites.xlsx ec2-user@your-server:/var/www/approved-websites/
```

### 4. **Service Configuration**
```bash
# Create systemd service file
sudo nano /etc/systemd/system/approved-websites.service
```

**Service file content:**
```ini
[Unit]
Description=Approved Websites System
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/var/www/approved-websites
ExecStart=/usr/bin/python3 /var/www/approved-websites/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable approved-websites
sudo systemctl start approved-websites
sudo systemctl status approved-websites
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

### 1. **File Permissions**
```bash
# Set proper permissions
sudo chmod 644 /var/www/approved-websites/*.py
sudo chmod 644 /var/www/approved-websites/*.html
sudo chmod 600 /var/www/reports/site_reports.json
sudo chmod 755 /var/www/reports/backups/
```

### 2. **Firewall Rules**
```bash
# Configure firewall (if using)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### 3. **Access Control**
```bash
# Restrict admin dashboard access
# Add IP restrictions in server.py or use AWS Security Groups
```

## 📊 **Data Management**

### 1. **Backup Strategy**
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
cp /var/www/reports/site_reports.json /var/www/reports/backups/daily_backup_$DATE.json

# Weekly backup to S3 (optional)
aws s3 cp /var/www/reports/site_reports.json s3://your-bucket/reports/weekly_backup_$DATE.json
```

### 2. **Log Monitoring**
```bash
# View service logs
sudo journalctl -u approved-websites -f

# View application logs
tail -f /var/log/approved-websites.log
```

### 3. **Data Export**
```bash
# Export reports for analysis
python3 -c "
import json
with open('/var/www/reports/site_reports.json', 'r') as f:
    reports = json.load(f)
print(f'Total reports: {len(reports)}')
for report in reports:
    print(f'{report[\"site_name\"]} - {report[\"issue_type\"]}')
"
```

## 🔧 **Maintenance Tasks**

### 1. **Update Website List**
```bash
# Upload new Excel file
scp -i your-key.pem new_whitelist.xlsx ec2-user@your-server:/var/www/approved-websites/

# Regenerate HTML
cd /var/www/approved-websites
python3 main.py

# Restart service
sudo systemctl restart approved-websites
```

### 2. **Monitor System**
```bash
# Check service status
sudo systemctl status approved-websites

# Check disk space
df -h

# Check memory usage
free -h

# Check reports count
wc -l /var/www/reports/site_reports.json
```

### 3. **Security Updates**
```bash
# Update system packages
sudo yum update -y

# Update Python packages
pip3 install --upgrade pandas openpyxl

# Restart service after updates
sudo systemctl restart approved-websites
```

## 🌐 **Access URLs**

### **For Users (Incarcerated Students):**
- `http://your-aws-server/` - Main website listing
- Clean interface, no access to reports

### **For IT Staff:**
- `http://your-aws-server/admin` - Admin dashboard
- View all reports, statistics, export data

## ⚠️ **Important Security Notes**

1. **Network Isolation**: Ensure server is only accessible from prison network
2. **Regular Backups**: Set up automated backups to S3 or local storage
3. **Access Logs**: Monitor who accesses the admin dashboard
4. **File Permissions**: Keep reports directory secure
5. **Service Monitoring**: Monitor service health and restart if needed

## 🚨 **Troubleshooting**

### **Service Won't Start:**
```bash
# Check logs
sudo journalctl -u approved-websites -n 50

# Check file permissions
ls -la /var/www/approved-websites/

# Test manually
cd /var/www/approved-websites
python3 server.py
```

### **Reports Not Saving:**
```bash
# Check directory permissions
ls -la /var/www/reports/

# Check disk space
df -h

# Test file write
echo "test" > /var/www/reports/test.txt
```

### **Admin Dashboard Not Loading:**
```bash
# Check if service is running
sudo systemctl status approved-websites

# Check port binding
netstat -tlnp | grep :80

# Test local access
curl http://localhost/admin
```

---

**This setup provides a secure, scalable solution for your prison environment with complete data control and IT oversight.**





