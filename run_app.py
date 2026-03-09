#!/usr/bin/env python3
"""
Launch script for Approved Websites system
Generates HTML and starts secure server
"""

import subprocess
import sys
from pathlib import Path


def find_latest_csv(pattern="SharePoint_List_Export_*.csv") -> Path | None:
    """
    Find the most recently modified CSV matching the given pattern
    in the current working directory.
    """
    candidates = sorted(
        Path(".").glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def generate_html():
    """Generate the HTML file via build_approved_sites.py"""
    script_name = Path(sys.argv[0]).name or "run_app.py"
    print("📄 Generating website listing...")

    # Anything passed to run_app.py after its name is forwarded to build_approved_sites.py.
    # Example:
    #   python run_app.py SharePoint_List_Export_20251208_145101.csv
    #   python run_app.py SharePoint_List_Export_20251208_145101.csv --no-embed-favicons
    extra_args = sys.argv[1:]

    if extra_args:
        # User explicitly gave args; just forward them to build_approved_sites.py
        main_args = extra_args
        print(f"➡️  Forwarding arguments to build_approved_sites.py: {main_args!r}")
    else:
        # No args: try to auto-detect the latest SharePoint export
        latest = find_latest_csv()
        if not latest:
            print("❌ No CSV found matching 'SharePoint_List_Export_*.csv' in the current directory.")
            print("   Please either:")
            print(f"     • Run: python {script_name} <path-to-csv>")
            print("       or")
            print("     • Place a SharePoint_List_Export_*.csv file in this folder.")
            return False
        main_args = [str(latest)]
        print(f"🧾 Detected latest CSV: {latest}")

    try:
        cmd = [sys.executable, "build_approved_sites.py"] + main_args
        print(f"▶️  Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ HTML generated successfully")
            if result.stdout.strip():
                print(result.stdout)
        else:
            print("❌ Error generating HTML:")
            if result.stdout.strip():
                print("STDOUT:")
                print(result.stdout)
            if result.stderr.strip():
                print("STDERR:")
                print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ Error running build_approved_sites.py: {e}")
        return False

    return True


def start_server():
    """Start the secure server"""
    print("🚀 Starting secure server...")
    try:
        subprocess.run([sys.executable, "web_server.py"])
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
