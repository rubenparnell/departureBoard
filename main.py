import time
import os
import subprocess
import json
import qrcode
import threading
import requests
from flask import Flask, render_template, request, redirect, url_for
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import RGBMatrix, RGBMatrixOptions

# Initialize Flask
app = Flask(__name__)

SETTINGS_FILE = "settings.json"

# Default settings
default_settings = {
    "station1": "TYN",
    "platform1": "1",
    "station1": "TYN",
    "platform1": "2"
}

# Ensure settings file exists
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(default_settings, f)

# Load settings
def load_settings():
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

# Save settings
def save_settings(station1, platform1, station2, platform2):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"station1": station1, "platform1": platform1, "station2": station2, "platform2": platform2}, f)

# LED Matrix setup
options = RGBMatrixOptions()
options.rows = 48
options.cols = 96
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'
options.brightness = 100
options.pwm_lsb_nanoseconds = 130
options.pwm_bits = 11
options.gpio_slowdown = 2

matrix = RGBMatrix(options=options)
font = ImageFont.truetype("./5x8.bdf", 8)
font_size = 8

smallFont = ImageFont.truetype("./4x6.bdf", 6)
smallFontHeight = 6

destinationColour = (246, 115, 25)
stationColour = (6, 234, 49)

# Wi-Fi check
def check_wifi():
    try:
        subprocess.check_call(['ping', '-c', '1', '8.8.8.8'])
        return True
    except subprocess.CalledProcessError:
        return False

# Display QR code for Wi-Fi setup
def display_qr_code():
    wifi_setup_url = "http://departurepizero:5000/setup"
    qr = qrcode.make(wifi_setup_url)
    img = qr.resize((matrix.width, matrix.height))
    matrix.SetImage(img.convert('RGB'))
    time.sleep(10)

# Fetch station names
stations = json.loads(requests.get("https://metro-rti.nexus.org.uk/api/stations").text)

# Get train data
def get_trains(station, platform):
    try:
        response = requests.get(f"https://metro-rti.nexus.org.uk/api/times/{station}/{platform}")
        return json.loads(response.text)[:2]
    except:
        return []

# Flask routes
@app.route('/')
def departure_board():
    settings = load_settings()
    return render_template('departure_board.html', station1=settings["station1"], platform1=settings["platform1"], station2=settings["station2"], platform2=settings["platform2"])

@app.route('/setup', methods=['GET', 'POST'])
def setup_wifi():
    if request.method == 'POST':
        ssid = request.form['ssid']
        password = request.form['password']
        with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'a') as f:
            f.write(f'\nnetwork={{\n\tssid="{ssid}"\n\tpsk="{password}"\n}}\n')
        subprocess.call(['sudo', 'reboot'])
    return render_template('setup.html')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        station1 = request.form['station1']
        platform1 = request.form['platform1']
        station2 = request.form['station2']
        platform2 = request.form['platform2']
        save_settings(station1, platform1, station2, platform2)
        return redirect(url_for('departure_board'))
    settings = load_settings()
    return render_template('settings.html', station1=settings["station1"], platform1=settings["platform1"], station2=settings["station2"], platform2=settings["platform2"])

# Flask thread
def run_flask():
    app.run(host='0.0.0.0', port=5000)

# Display departure board
def show_departure_board():
    current_time = int(time.time())

    while True:
        # Create blank image
        image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        lowest_pixel = 1

        if current_time % 10 == 0:
            settings = load_settings()
            station_code1 = settings['station1']
            platform1 = settings['platform1']
            station_code2 = settings['station2']
            platform2 = settings['platform2']

            if station_code1 in stations and station_code2 in stations:
                station_name1 = stations[station_code1]
                station_name2 = stations[station_code2]
            else:
                station_name1 = "Unknown"
                station_name2 = "Unknown"

            print("got new settings")

        if current_time % 30 == 0:
            trains1 = get_trains(station_name1, platform1)
            trains2 = get_trains(station_name2, platform2)

            print("got new train times")

        # Draw station and platform
        draw.text((1, lowest_pixel), f"{station_name1}: {platform1}", font=smallFont, fill=stationColour)
        lowest_pixel += smallFontHeight

        # Draw train departures
        for i, train in enumerate(trains1):
            destination = train[0]

            if len(destination) > 15:
                displayFont = smallFont
                if i == 0:
                    lowestPixel += 1
            else:
                displayFont = font

            text_position = (1, lowestPixel)

            draw.text(text_position, destination, font=displayFont, fill=destinationColour)
            
            due = str(train[1])
            if due == "0":
                due = "Due"
            elif due == "-1":
                due = "Due"
                
            if len(destination) > 15:
                text_position = (matrix.width-5*len(due), lowestPixel-1)
            else:
                text_position = (matrix.width-5*len(due), lowestPixel)
                
            draw.text(text_position, due, font=font, fill=destinationColour)

            lowestPixel += font_size
            
        if len(trains1) == 0:
            lowestPixel += 2
            text = "There are no services"
            draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=destinationColour)
            lowestPixel += smallFontHeight+1
            
            text = "from this platform"
            draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=destinationColour)

        # Draw Line Separator:
        lowestPixel = 24
        line_position = (0, lowestPixel, matrix.width, lowestPixel)
        lowestPixel += 2

        draw.line(line_position, fill=destinationColour, width=1)


        # Display 2nd info:
        draw.text((1, lowestPixel), f"{station_name2}: {platform2}", font=smallFont, fill=stationColour)
        lowestPixel += smallFontHeight

        for i, train in enumerate(trains2):
            destination = train[0]

            if len(destination) > 15:
                displayFont = smallFont
                if i == 0:
                    lowestPixel += 1
            else:
                displayFont = font

            text_position = (1, lowestPixel)

            draw.text(text_position, destination, font=displayFont, fill=destinationColour)

            due = str(train[1])
            if due == "0":
                due = "Due"
            elif due == "-1":
                due = "Due"

            if len(destination) > 15:
                text_position = (matrix.width-5*len(due), lowestPixel-1)
            else:
                text_position = (matrix.width-5*len(due), lowestPixel)

            draw.text(text_position, due, font=font, fill=destinationColour)

            lowestPixel += font_size

        if len(trains2) == 0:
            lowestPixel += 2
            text = "There are no services"
            draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=destinationColour)
            lowestPixel += smallFontHeight+1

            text = "from this platform"
            draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=destinationColour)

        # Display the image
        matrix.SetImage(image.convert('RGB'))

        time.sleep(1)

# Main function
def main():
    if check_wifi():
        print("Wi-Fi connected.")
        threading.Thread(target=run_flask, daemon=True).start()
        show_departure_board()
    else:
        print("No Wi-Fi detected. Showing QR code.")
        display_qr_code()

if __name__ == '__main__':
    main()