import os
import json
import threading
import requests
from flask import Flask, render_template, request
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import RGBMatrix, RGBMatrixOptions

# Initialize Flask
app = Flask(__name__)

SETTINGS_FILE = "settings.json"
update_event = threading.Event()

# Default settings
default_settings = {
    "station1": "TYN",
    "platform1": "1",
    "station2": "TYN",
    "platform2": "2"
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
    update_event.set()  # Notify display thread of changes

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
options.disable_hardware_pulsing = True

matrix = RGBMatrix(options=options)
font = ImageFont.truetype("./5x8.bdf", 8)
font_size = 8

smallFont = ImageFont.truetype("./4x6.bdf", 6)
smallFontHeight = 6

destinationColour = (246, 115, 25)
stationColour = (6, 234, 49)

# Fetch station names
stations = json.loads(requests.get("https://metro-rti.nexus.org.uk/api/stations").text)

def get_trains(station, platform):
    try:
        response = requests.get(f"https://metro-rti.nexus.org.uk/api/times/{station}/{platform}")
        return json.loads(response.text)[:2]
    except:
        return []

def convertStationCode(code):
    return stations.get(code, "Unknown")

# Flask routes
@app.route('/', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        station1 = request.form['station1']
        platform1 = request.form['platform1']
        station2 = request.form['station2']
        platform2 = request.form['platform2']
        save_settings(station1, platform1, station2, platform2)

    settings = load_settings()

    # Convert station codes to names for pre-filled form values
    station1_name = convertStationCode(settings["station1"])
    station2_name = convertStationCode(settings["station2"])

    return render_template(
        'settings.html',
        stations=stations,  # Pass station list to the template
        station1_code=settings["station1"],
        station1_name=station1_name,
        platform1=settings["platform1"],
        station2_code=settings["station2"],
        station2_name=station2_name,
        platform2=settings["platform2"]
    )

# Flask thread
def run_flask():
    app.run(host='0.0.0.0', port=80)

def show_departure_board():
    while True:
        settings = load_settings()
        station_code1, platform1 = settings['station1'], settings['platform1']
        station_code2, platform2 = settings['station2'], settings['platform2']

        while not update_event.is_set():  # Loop until settings change
            lowestPixel = 1
            trains1, trains2 = get_trains(station_code1, platform1), get_trains(station_code2, platform2)
            print("fetched trains")
            
            image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
            draw = ImageDraw.Draw(image)
            
            # Draw station and platform
            draw.text((1, lowestPixel), f"{convertStationCode(station_code1)}: {platform1}", font=smallFont, fill=stationColour)
            lowestPixel += smallFontHeight

            # Draw train departures
            for i, train in enumerate(trains1):
                destination = train['destination']

                if len(destination) > 15:
                    displayFont = smallFont
                    if i == 0:
                        lowestPixel += 1
                else:
                    displayFont = font

                text_position = (1, lowestPixel)

                draw.text(text_position, destination, font=displayFont, fill=destinationColour)
                
                due = str(train['dueIn'])
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
            draw.text((1, lowestPixel), f"{convertStationCode(station_code2)}: {platform2}", font=smallFont, fill=stationColour)
            lowestPixel += smallFontHeight

            for i, train in enumerate(trains2):
                destination = train['destination']

                if len(destination) > 15:
                    displayFont = smallFont
                    if i == 0:
                        lowestPixel += 1
                else:
                    displayFont = font

                text_position = (1, lowestPixel)

                draw.text(text_position, destination, font=displayFont, fill=destinationColour)

                due = str(train['dueIn'])
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
            
            matrix.SetImage(image.convert('RGB'))

            # Wait for 30 seconds or break early if settings change
            if update_event.wait(30):  # If update_event is set, break loop early
                update_event.clear()
                break  # Reload settings immediately


# Main function
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    show_departure_board()

if __name__ == '__main__':
    main()
