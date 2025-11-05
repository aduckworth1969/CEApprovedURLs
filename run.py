#!/usr/bin/env python3
"""
Launch script for Approved Websites system
Generates HTML and starts secure server
"""

import subprocess
import sys
import os
import time
import webbrowser
from threading import Thread

def generate_html():
    """Generate the HTML file"""
    print("📄 Generating website listing...")
    try:
        result = subprocess.run([sys.executable, "main.py"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ HTML generated successfully")
            print(result.stdout)
        else:
            print("❌ Error generating HTML:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ Error running main.py: {e}")
        return False
    return True

def start_server():
    """Start the secure server"""
    print("🚀 Starting secure server...")
    try:
        subprocess.run([sys.executable, "server.py"])
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

def main():
    """Main function"""
    print("🎯 Approved Websites System")
    print("=" * 50)
    
    # Generate HTML first
    if not generate_html():
        print("❌ Failed to generate HTML. Exiting.")
        return
    
    print("\n" + "=" * 50)
    
    # Start server
    start_server()

if __name__ == '__main__':
    main()





