import subprocess
import time
import os

def check_wifi():
    try:
        output = subprocess.check_output(["hostname", "-I"])
        return bool(output.strip())
    except subprocess.CalledProcessError:
        return False

while True:
    if check_wifi():
        os.system("sudo systemctl stop wifi-setup.service")
        os.system("sudo systemctl disable wifi-setup.service")
        os.system("sudo systemctl stop hostapd")
        os.system("sudo systemctl stop dnsmasq")
        os.system("sudo systemctl start departureboard-web.service")
        break
    else:
        os.system("sudo systemctl start wifi-setup.service")
        os.system("sudo systemctl start hostapd")
        os.system("sudo systemctl start dnsmasq")
        os.system("python3 /home/ruben/departureBoard/display_qr.py")  # Show QR code

    time.sleep(10)
