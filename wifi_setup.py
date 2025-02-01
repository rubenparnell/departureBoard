from flask import Flask, render_template, request
import subprocess

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def wifi_setup():
    if request.method == "POST":
        ssid = request.form["ssid"]
        password = request.form["password"]
        
        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "a") as f:
            f.write(f'\nnetwork={{\n    ssid="{ssid}"\n    psk="{password}"\n}}\n')

        subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"])

        return "Wi-Fi credentials saved. Restarting..."
    
    return """
    <form method="post">
        SSID: <input type="text" name="ssid"><br>
        Password: <input type="password" name="password"><br>
        <input type="submit" value="Connect">
    </form>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
