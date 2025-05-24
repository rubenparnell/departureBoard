import os
import json
import threading
import requests
from flask import Flask, render_template, request
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from signal import pause
from gpiozero import LED, Button
from datetime import datetime
import time
from io import BytesIO

from get_films import get_jamjar_films

MODES = ["metro", "weather", "weather_graph", "films", "off"]
current_mode = 0  # Start with "metro"

# Setup button and LED
button = Button(21, bounce_time=0.2)  # 200 ms debounce time
led = LED(26)

# Initialize Flask
app = Flask(__name__)

SETTINGS_FILE = "settings.json"
update_event = threading.Event()

# Default settings
default_settings = {
    "station1": "TYN",
    "platform1": "1",
    "station2": "TYN",
    "platform2": "2",
    "LAT": 0.0,
    "LON": 0.0,
    "FORECAST_HOURS": [9, 12, 15, 18]
}

# Ensure settings file exists
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(default_settings, f)

# Load settings
def load_settings():
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

settings = load_settings()

# Save settings
def save_settings(station1, platform1, station2, platform2, lat, lon, forecast_hours):
    # Convert forecast_hours string to list of integers
    try:
        forecast_hours_list = [int(h.strip()) for h in forecast_hours.split(',') if h.strip().isdigit()]
    except Exception:
        forecast_hours_list = default_settings["FORECAST_HOURS"]
    
    with open(SETTINGS_FILE, "w") as f:
        json.dump({
            "station1": station1,
            "platform1": platform1,
            "station2": station2,
            "platform2": platform2,
            "LAT": float(lat),
            "LON": float(lon),
            "FORECAST_HOURS": forecast_hours_list
        }, f)
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

primaryColour = (246, 115, 25)
secondaryColour = (6, 234, 49)

rainColour = (33, 227, 253)
tempColour = (252, 238, 70)

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
        lat = request.form.get('lat', 0)
        lon = request.form.get('lon', 0)
        forecast_hours = request.form.get('forecast_hours', "9,12,15,18")
        save_settings(station1, platform1, station2, platform2, lat, lon, forecast_hours)

    settings = load_settings()

    # Convert station codes to names for pre-filled form values
    station1_name = convertStationCode(settings["station1"])
    station2_name = convertStationCode(settings["station2"])

    # Convert forecast hours list to comma-separated string for form input
    forecast_hours_str = ",".join(str(h) for h in settings.get("FORECAST_HOURS", []))

    return render_template(
        'settings.html',
        stations=stations,  # Pass station list to the template
        station1_code=settings["station1"],
        station1_name=station1_name,
        platform1=settings["platform1"],
        station2_code=settings["station2"],
        station2_name=station2_name,
        platform2=settings["platform2"],
        lat=settings.get("LAT", 0.0),
        lon=settings.get("LON", 0.0),
        forecast_hours=forecast_hours_str
    )

# Flask thread
def run_flask():
    app.run(host='0.0.0.0', port=80)

# Screen control flag
screen_on = True

def cycle_mode():
    global current_mode
    current_mode = (current_mode + 1) % len(MODES)
    print(f"Switched to mode: {MODES[current_mode]}")
    update_event.set()

# Button setup to toggle screen on/off
button.when_pressed = cycle_mode
    

def showMetro():
    station_code1, platform1 = settings['station1'], settings['platform1']
    station_code2, platform2 = settings['station2'], settings['platform2']

    lowestPixel = 1
    trains1, trains2 = get_trains(station_code1, platform1), get_trains(station_code2, platform2)
    print("Fetched trains")
    
    image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Draw station and platform
    draw.text((1, lowestPixel), f"{convertStationCode(station_code1)}: {platform1}", font=smallFont, fill=secondaryColour)
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
        draw.text(text_position, destination, font=displayFont, fill=primaryColour)
        
        due = str(train['dueIn'])
        if due == "0":
            due = "Due"
        elif due == "-1":
            due = "Due"
            
        if len(destination) > 15:
            text_position = (matrix.width-5*len(due), lowestPixel-1)
        else:
            text_position = (matrix.width-5*len(due), lowestPixel)
            
        draw.text(text_position, due, font=font, fill=primaryColour)

        lowestPixel += font_size
        
    if len(trains1) == 0:
        lowestPixel += 2
        text = "There are no services"
        draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=primaryColour)
        lowestPixel += smallFontHeight+1
        
        text = "from this platform"
        draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=primaryColour)

    # Draw Line Separator:
    lowestPixel = 24
    line_position = (0, lowestPixel, matrix.width, lowestPixel)
    lowestPixel += 2

    draw.line(line_position, fill=primaryColour, width=1)

    # Display 2nd info:
    draw.text((1, lowestPixel), f"{convertStationCode(station_code2)}: {platform2}", font=smallFont, fill=secondaryColour)
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
        draw.text(text_position, destination, font=displayFont, fill=primaryColour)

        due = str(train['dueIn'])
        if due == "0":
            due = "Due"
        elif due == "-1":
            due = "Due"

        if len(destination) > 15:
            text_position = (matrix.width-5*len(due), lowestPixel-1)
        else:
            text_position = (matrix.width-5*len(due), lowestPixel)

        draw.text(text_position, due, font=font, fill=primaryColour)

        lowestPixel += font_size

    if len(trains2) == 0:
        lowestPixel += 2
        text = "There are no services"
        draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=primaryColour)
        lowestPixel += smallFontHeight+1

        text = "from this platform"
        draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=primaryColour)

    return image


weather_cache = {
    "timestamp": 0,
    "data": None
}

last_forecast_data = None
last_rendered_image = None

with open("weather_icons.json") as f:
    weather_icons = json.load(f)


def get_icon(code, is_daytime, icon_size):
    print(f"Fetching icon for code: {code}, is_daytime: {is_daytime}")
    time_of_day = "day" if is_daytime else "night"
    icon_url = weather_icons.get(str(code), {}).get(time_of_day, {}).get("image")
    if not icon_url:
        print("No icon found for this weather code.")
        return None

    try:
        response = requests.get(icon_url)
        icon = Image.open(BytesIO(response.content)).convert("RGBA")
        return icon.resize(icon_size)
    except Exception as e:
        print(f"Error loading icon: {e}")
        return None


def get_weather_forecast():
    global weather_cache

    now = time.time()
    if weather_cache["data"] and now - weather_cache["timestamp"] < 600:
        return weather_cache["data"]

    today = datetime.now().date()
    start = today.strftime("%Y-%m-%dT00:00")
    end = today.strftime("%Y-%m-%dT23:00")

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={settings['LAT']}&longitude={settings['LON']}"
        f"&hourly=temperature_2m,precipitation_probability,weathercode"
        f"&start={start}&end={end}"
        f"&timezone=Europe%2FLondon"
    )

    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        weather_cache["data"] = data
        weather_cache["timestamp"] = now
        return data
    except Exception as e:
        print("Weather fetch error:", e)
        return None


def extract_forecast_data(data):
    hours = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    precipitation_probs = data["hourly"]["precipitation_probability"]
    codes_data = data["hourly"]["weathercode"]

    now = datetime.now()
    result = {}

    for i, t in enumerate(hours):
        dt = datetime.fromisoformat(t)
        if dt.hour in settings["FORECAST_HOURS"] and dt.date() == now.date():
            result[dt.hour] = {
                "temp": temps[i],
                "precipitation_probability": precipitation_probs[i],
                "code": codes_data[i],
                "is_day": 6 <= dt.hour <= 18
            }
    return result


def showWeather():
    print("Showing weather forecast...")
    global matrix, last_forecast_data, last_rendered_image

    data = get_weather_forecast()
    if not data:
        return

    time_data = extract_forecast_data(data)

    # Skip update if forecast hasn't changed
    if time_data == last_forecast_data:
        return last_rendered_image

    last_forecast_data = time_data

    image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    col_width = matrix.width // 4
    y_start = 1

    for i, hour in enumerate(settings["FORECAST_HOURS"]):
        x = i * col_width
        if hour not in time_data:
            continue

        forecast = time_data[hour]
        temp = forecast["temp"]
        precipitation_prob = forecast["precipitation_probability"]
        code = forecast["code"]
        is_day = forecast["is_day"]

        draw.text((x + 1, y_start), f"{hour}:00", font=smallFont, fill=(255, 255, 255))
        draw.text((x + 1, y_start + 10), f"{round(temp)}°", font=smallFont, fill=(255, 255, 255))
        draw.text((x + 1, y_start + 18), f"{precipitation_prob}%", font=smallFont, fill=(255, 255, 255))

        icon = get_icon(code, is_day, icon_size=(24, 24))
        if icon:
            image.paste(icon, (x, y_start + 22), icon)

    last_rendered_image = image
    return image


def showWeatherGraph():
    global matrix

    data = get_weather_forecast()
    if not data:
        return

    hours = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    precipitation_probs = data["hourly"]["precipitation_probability"]
    codes = data["hourly"]["weathercode"]

    now = datetime.now()
    today = now.date()

    # Filter data for today
    times = []
    today_temps = []
    today_precip = []
    for i, t in enumerate(hours):
        dt = datetime.fromisoformat(t)
        if dt.date() == today:
            times.append(dt)
            today_temps.append(temps[i])
            today_precip.append(precipitation_probs[i])

    if not times:
        return None

    # Define sizes
    side_panel_width = 18
    graph_width = matrix.width - side_panel_width + 2
    height = matrix.height

    # Create image
    image = Image.new("RGB", (matrix.width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Ranges
    min_temp = min(today_temps)
    max_temp = max(today_temps)
    temp_range = max_temp - min_temp or 1  # Avoid divide-by-zero

    start_hour = 0
    end_hour = 23
    total_hours = end_hour - start_hour + 1

    def scale_x(hour):
        return int((hour - start_hour) / total_hours * graph_width)

    def scale_y_temp(temp):
        return int(height - ((temp - min_temp) / temp_range * height))

    def scale_y_precip(prob):
        return int(height - (prob / 100 * height))

    # Draw temperature line
    for i in range(1, len(times)):
        x1 = scale_x(times[i - 1].hour)
        y1 = scale_y_temp(today_temps[i - 1])
        x2 = scale_x(times[i].hour)
        y2 = scale_y_temp(today_temps[i])
        draw.line((x1, y1, x2, y2), fill=tempColour, width=1)

    # Draw precipitation line
    for i in range(1, len(times)):
        x1 = scale_x(times[i - 1].hour)
        y1 = scale_y_precip(today_precip[i - 1])
        x2 = scale_x(times[i].hour)
        y2 = scale_y_precip(today_precip[i])
        draw.line((x1, y1, x2, y2), fill=rainColour, width=1)

    # Draw current time marker
    current_x = scale_x(now.hour + now.minute / 60)
    draw.line((current_x, 0, current_x, height), fill=primaryColour, width=1)

    # --- SIDE PANEL ---
    panel_x = matrix.width - side_panel_width

    # Current temperature and precipitation
    current_temp = None
    current_precip = None
    for i, dt in enumerate(times):
        if dt.hour == now.hour:
            current_temp = round(today_temps[i])
            current_precip = round(today_precip[i])
            break
    if current_temp is None:
        current_temp = round(today_temps[-1])
    if current_precip is None:
        current_precip = round(today_precip[-1])

    draw.line((panel_x-1, 0, panel_x-1, height), fill=secondaryColour, width=1)

    # Draw temperatures
    draw.text((panel_x + 1, 0), datetime.now().strftime("%H:%M"), font=smallFont, fill=primaryColour)
    draw.text((panel_x + 1, 7), f"{round(current_temp)}°", font=smallFont, fill=tempColour)
    draw.text((panel_x + 1, 13), f"↑{round(max_temp)}°", font=smallFont, fill=(255, 0, 0))
    draw.text((panel_x + 1, 19), f"↓{round(min_temp)}°", font=smallFont, fill=(0, 0, 255))
    draw.text((panel_x + 1, 27), f"{round(current_precip)}%", font=smallFont, fill=rainColour)

    return image

film_cache = {
    "date": None,
    "data": None
}

def showFilms(scroll_offset=0, page=0):
    global film_cache, matrix

    today = datetime.now().date()

    if film_cache["date"] != today:
        film_data = get_jamjar_films()
        
        film_cache["data"] = film_data
        film_cache["date"] = today
    else:
        film_data = film_cache["data"]

    if not film_data:
        return None

    image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    pause_frames = 40  # ~2s at 20fps
    films_per_page = matrix.height // 6 // 2  # 2 lines per film, 6px per line

    films = list(film_data.items())
    total_pages = (len(films) + films_per_page - 1) // films_per_page
    page = page % total_pages

    start = page * films_per_page
    end = start + films_per_page
    visible_films = films[start:end]

    y = 0
    for title, times in visible_films:
        text_width = int(smallFont.getlength(title))
        if text_width <= matrix.width:
            draw.text((0, y), title, font=smallFont, fill=primaryColour)
        else:
            max_scroll = text_width - matrix.width
            total_cycle = pause_frames + max_scroll + pause_frames
            scroll_pos = scroll_offset % total_cycle

            if scroll_pos < pause_frames:
                draw.text((0, y), title, font=smallFont, fill=primaryColour)
            elif scroll_pos < pause_frames + max_scroll:
                offset = scroll_pos - pause_frames
                draw.text((-offset, y), title, font=smallFont, fill=primaryColour)
            else:
                draw.text((-max_scroll, y), title, font=smallFont, fill=primaryColour)

        y += 6
        times_str = ", ".join(times)
        draw.text((0, y), times_str[:matrix.width // 4], font=smallFont, fill=secondaryColour)
        y += 6
        
    draw.text((matrix.width-4*3, matrix.height-5), f"{page+1}/{total_pages}", font=smallFont, fill=rainColour)

    return image


def show_board():
    global current_mode

    scroll_offset = 0
    page_counter = 0
    page = 0

    while True:
        mode = MODES[current_mode]

        if mode == "metro":
            led.on()
            image = showMetro()
            matrix.SetImage(image.convert('RGB'))
            wait_time = 30

        elif mode == "weather":
            led.on()
            image = showWeather()
            matrix.SetImage(image.convert('RGB'))
            wait_time = 30

        elif mode == "weather_graph":
            led.on()
            image = showWeatherGraph()
            matrix.SetImage(image.convert('RGB'))
            wait_time = 30

        elif mode == "films":
            led.on()
            image = showFilms(scroll_offset, page)
            matrix.SetImage(image.convert('RGB'))

            scroll_offset += 1
            page_counter += 1

            if page_counter >= 400:
                page_counter = 0
                page += 1

            wait_time = 0.08

        elif mode == "off":
            matrix.Clear()
            led.off()
            update_event.wait()
            update_event.clear()
            continue

        if update_event.wait(wait_time):
            update_event.clear()


# Main function
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    show_board()

if __name__ == '__main__':
    main()
