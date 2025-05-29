import os
import json
import threading
import requests
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from signal import pause
from gpiozero import LED, Button
from datetime import datetime
import time
from io import BytesIO
import paho.mqtt.client as mqtt
import ssl
from dotenv import load_dotenv
import subprocess
import qrcode
import warnings
import textwrap
from flask import Flask, render_template, request, redirect, url_for
from get_films import get_jamjar_films

warnings.filterwarnings("ignore", category=DeprecationWarning)

# SETUP VARIABLES
load_dotenv()  # Load environment variables from .env file

client = None 
mqtt_connected = threading.Event()

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
BOARD_ID = os.getenv("BOARD_ID")
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

MODES = ["messages", "metro", "weather", "weather_graph", "films", "link", "off"]
current_mode = 0
force_refresh_messages = False

# Setup button and LED
button = Button(21, bounce_time=0.2)  # 200 ms debounce time
led = LED(26)

SETTINGS_FILE = "settings.json"
update_event = threading.Event()

# Default settings
default_settings = {
    "station1": "TYN",
    "platform1": "1",
    "station2": "TYN",
    "platform2": "2",
    "lat": 0.0,
    "lon": 0.0,
    "forecast_hours": [9, 12, 15, 18]
}

# Ensure settings file exists
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(default_settings, f)

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
uvColour = (253, 72, 34)

# Fetch station names
stations = json.loads(requests.get("https://metro-rti.nexus.org.uk/api/stations").text)


# FUNCTIONS:

# Check if Pi is connected to Wi-Fi
def check_wifi():
    try:
        subprocess.check_call(['ping', '-c', '1', '8.8.8.8'])
        return True
    except subprocess.CalledProcessError:
        return False

# Create an access point for Wi-Fi setup
def create_access_point():
    subprocess.call(['sudo', 'systemctl', 'stop', 'dhcpcd.service'])
    subprocess.call(['sudo', 'systemctl', 'disable', 'dhcpcd.service'])
    
    # Set up the access point using hostapd and dnsmasq
    subprocess.call(['sudo', 'systemctl', 'start', 'hostapd.service'])
    subprocess.call(['sudo', 'systemctl', 'start', 'dnsmasq.service'])

# Stop the access point when Wi-Fi is connected
def stop_access_point():
    subprocess.call(['sudo', 'systemctl', 'stop', 'hostapd.service'])
    subprocess.call(['sudo', 'systemctl', 'stop', 'dnsmasq.service'])
    subprocess.call(['sudo', 'systemctl', 'start', 'dhcpcd.service'])

# Set up Wi-Fi credentials
def set_wifi_credentials(ssid, password):
    with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'a') as f:
        f.write(f'\nnetwork={{\n\tssid="{ssid}"\n\tpsk="{password}"\n}}\n')
    subprocess.call(['sudo', 'reboot'])

# Display QR code for Wi-Fi setup
def display_qr_code():
    wifi_setup_url = "http://localhost:5000"  # URL for the Flask app
    qr = qrcode.make(wifi_setup_url)
    img = qr.resize((min(matrix.width, matrix.height),min(matrix.width, matrix.height)))
    matrix.SetImage(img.convert('RGB'))
    time.sleep(10)

# Load settings
def load_settings():
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with result code", rc)
    client.subscribe(f"boards/{BOARD_ID}/#")
    mqtt_connected.set()

def on_message(client, userdata, msg):
    global current_mode, force_refresh_messages
    print(f"MQTT message received on topic {msg.topic}")
    if msg.topic == f"/board/{BOARD_ID}/settings":
        try:
            payload = json.loads(msg.payload.decode())
            save_settings(
                station1=payload.get("station1", settings["station1"]),
                platform1=payload.get("platform1", settings["platform1"]),
                station2=payload.get("station2", settings["station2"]),
                platform2=payload.get("platform2", settings["platform2"]),
                lat=payload.get("lat", settings["lat"]),
                lon=payload.get("lon", settings["lon"]),
                forecast_hours=",".join(map(str, payload.get("forecast_hours", settings["forecast_hours"])))
            )
            print("Settings updated from MQTT")
        except Exception as e:
            print("Failed to apply MQTT settings:", e)

    elif msg.topic == f"boards/{BOARD_ID}/message":
        if MODES[current_mode] == "messages":
            force_refresh_messages = True
            update_event.set()


def run_mqtt():
    global client

    client = mqtt.Client(client_id=BOARD_ID)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print(f"connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        client.loop_forever()
    except Exception as e:
        print("MQTT connection error:", e)

settings = load_settings()

# Save settings
def save_settings(station1, platform1, station2, platform2, lat, lon, forecast_hours):
    global settings
    # Convert forecast_hours string to list of integers
    try:
        forecast_hours_list = [int(h.strip()) for h in forecast_hours.split(',') if h.strip().isdigit()]
    except Exception:
        forecast_hours_list = default_settings["forecast_hours"]

    print(f"Saving settings: {station1}, {platform1}, {station2}, {platform2}, {lat}, {lon}, {forecast_hours_list}")
    
    with open(SETTINGS_FILE, "w") as f:
        json.dump({
            "station1": station1,
            "platform1": platform1,
            "station2": station2,
            "platform2": platform2,
            "lat": float(lat),
            "lon": float(lon),
            "forecast_hours": forecast_hours_list
        }, f)

    settings = load_settings()

    update_event.set()  # Notify display thread of changes

def get_trains(station, platform):
    try:
        response = requests.get(f"https://metro-rti.nexus.org.uk/api/times/{station}/{platform}")
        return json.loads(response.text)[:2]
    except:
        return []

def convertStationCode(code):
    return stations.get(code, "Unknown")


def cycle_mode():
    global current_mode
    current_mode = (current_mode + 1) % len(MODES)
    print(f"Switched to mode: {MODES[current_mode]}")
    update_event.set()

# Button setup to toggle screen on/off
button.when_pressed = cycle_mode



# FLASK WEB APP FOR WIFI SETUP:
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def setup_wifi():
    if request.method == 'POST':
        ssid = request.form['ssid']
        password = request.form['password']
        set_wifi_credentials(ssid, password)
        return redirect(url_for('departure_board'))
    return render_template('setup.html')

def run_flask():
    app.run(host='0.0.0.0', port=5000)



# DISPLAY FUNCTIONS:
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
    "lat": "",
    "lon": "",
    "data": None
}

last_forecast_data = None
last_rendered_image = None

with open("weather_icons.json") as f:
    weather_icons = json.load(f)


def get_icon(code, is_daytime, icon_size):
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
    global settings

    now = time.time()
    if weather_cache["data"] and now - weather_cache["timestamp"] < 600 and weather_cache["lon"] == settings["lon"] and weather_cache["lat"] == settings["lat"]:
        return weather_cache["data"]
    
    print("Fetching new weather data")

    today = datetime.now().date()
    start = today.strftime("%Y-%m-%dT00:00")
    end = today.strftime("%Y-%m-%dT23:00")

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={settings['lat']}&longitude={settings['lon']}"
        f"&hourly=temperature_2m,precipitation_probability,weathercode,uv_index,is_day"
        f"&start={start}&end={end}"
        f"&timezone=Europe%2FLondon"
    )

    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        weather_cache["data"] = data
        weather_cache["timestamp"] = now
        weather_cache["lon"] = settings["lon"]
        weather_cache["lat"] = settings["lat"]
        return data
    except Exception as e:
        print("Weather fetch error:", e)
        return None


def extract_forecast_data(data):
    hours = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    precipitation_probs = data["hourly"]["precipitation_probability"]
    codes_data = data["hourly"]["weathercode"]
    uv_index = data["hourly"]["uv_index"]
    is_day_array = data["hourly"]["is_day"]

    now = datetime.now()
    result = {}

    for i, t in enumerate(hours):
        dt = datetime.fromisoformat(t)
        if dt.hour in settings["forecast_hours"] and dt.date() == now.date():
            result[dt.hour] = {
                "temp": temps[i],
                "precipitation_probability": precipitation_probs[i],
                "code": codes_data[i],
                "uv_index": uv_index[i],
                "is_day": bool(is_day_array[i])
            }
    return result


def showWeather():
    print("Showing weather forecast...")
    global matrix, last_forecast_data, last_rendered_image

    data = get_weather_forecast()
    if not data:
        return

    time_data = extract_forecast_data(data)

    if time_data == last_forecast_data:
        return last_rendered_image

    last_forecast_data = time_data

    image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    col_width = matrix.width // 4
    y_start = 1

    for i, hour in enumerate(settings["forecast_hours"]):
        x = i * col_width
        if hour not in time_data:
            continue

        forecast = time_data[hour]
        temp = forecast["temp"]
        precipitation_prob = forecast["precipitation_probability"]
        code = forecast["code"]
        is_day = forecast["is_day"]
        uv_index = forecast["uv_index"]

        # Centre each text element horizontally
        hour_text = f"{hour}:00"
        temp_text = f"{round(temp)}°"
        precip_text = f"{precipitation_prob}%"
        uv_index_text = f"{uv_index}"

        hour_x = x + (col_width - smallFont.getlength(hour_text)) // 2
        temp_x = x + (col_width - smallFont.getlength(temp_text)) // 2
        precip_x = x + (col_width - smallFont.getlength(precip_text)) // 2
        uv_x = x + (col_width - smallFont.getlength(uv_index_text)) // 2

        draw.text((hour_x, y_start), hour_text, font=smallFont, fill=primaryColour)
        draw.text((temp_x, y_start + 8), temp_text, font=smallFont, fill=tempColour)
        draw.text((precip_x, y_start + 15), precip_text, font=smallFont, fill=rainColour)
        draw.text((uv_x, y_start + 22), uv_index_text, font=smallFont, fill=uvColour)

        # Paste and centre the icon
        icon = get_icon(code, is_day, icon_size=(24, 24))
        if icon:
            icon_x = x + (col_width - icon.width) // 2
            image.paste(icon, (icon_x, y_start + 24), icon)

        # Draw vertical column separator line (skip after last column)
        if i < 3:
            draw.line([(x + col_width - 1, 0), (x + col_width - 1, matrix.height)], fill=(50, 50, 50))

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
    uv_index = data["hourly"]["uv_index"]

    now = datetime.now()
    today = now.date()

    # Filter data for today
    times = []
    today_temps = []
    today_precip = []
    today_uv = []
    for i, t in enumerate(hours):
        dt = datetime.fromisoformat(t)
        if dt.date() == today:
            times.append(dt)
            today_temps.append(temps[i])
            today_precip.append(precipitation_probs[i])
            today_uv.append(uv_index[i])

    if not times:
        return None

    # Define sizes
    side_panel_width = 18
    graph_width = matrix.width - side_panel_width
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
    
    def scale_y_uv(uv):
        return int(height - (uv / 11 * height))

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

    # Draw UV line
    for i in range(1, len(times)):
        x1 = scale_x(times[i - 1].hour)
        y1 = scale_y_uv(today_uv[i - 1])
        x2 = scale_x(times[i].hour)
        y2 = scale_y_uv(today_uv[i])
        draw.line((x1, y1, x2, y2), fill=uvColour, width=1)


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
            current_uv = round(today_uv[i], 1)
            break
    if current_temp is None:
        current_temp = round(today_temps[-1])
    if current_precip is None:
        current_precip = round(today_precip[-1])
    if current_uv is None:
        current_uv = round(today_uv[-1], 1)

    draw.line((panel_x-1, 0, panel_x-1, height), fill=secondaryColour, width=1)

    # Draw temperatures
    draw.text((panel_x + 1, 0), datetime.now().strftime("%H:%M"), font=smallFont, fill=primaryColour)
    draw.text((panel_x + 1, 7), f"{round(current_temp)}°", font=smallFont, fill=tempColour)
    draw.text((panel_x + 1, 14), f"↑{round(max_temp)}°", font=smallFont, fill=(255, 0, 0))
    draw.text((panel_x + 1, 21), f"↓{round(min_temp)}°", font=smallFont, fill=(0, 0, 255))
    draw.text((panel_x + 1, 28), f"{round(current_precip)}%", font=smallFont, fill=rainColour)
    draw.text((panel_x + 1, 35), f"ƀ{current_uv}", font=smallFont, fill=uvColour) # ƀ is the uv symbol is the custom font

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

    image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    if not film_data:
        # Draw "No films found" message centred
        text = "No films found"
        text_width = int(smallFont.getlength(text))
        x = max((matrix.width - text_width) // 2, 0)
        y = max((matrix.height - 6) // 2, 0)
        draw.text((x, y), text, font=smallFont, fill=primaryColour)
        return image

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
        # Handle title scrolling
        title_width = int(smallFont.getlength(title))
        if title_width <= matrix.width:
            draw.text((0, y), title, font=smallFont, fill=primaryColour)
        else:
            max_scroll = title_width - matrix.width
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

        # Handle times scrolling
        times_str = ", ".join(times)
        times_width = int(smallFont.getlength(times_str))
        if times_width <= matrix.width:
            draw.text((0, y), times_str, font=smallFont, fill=secondaryColour)
        else:
            max_scroll = times_width - matrix.width
            total_cycle = pause_frames + max_scroll + pause_frames
            scroll_pos = scroll_offset % total_cycle

            if scroll_pos < pause_frames:
                draw.text((0, y), times_str, font=smallFont, fill=secondaryColour)
            elif scroll_pos < pause_frames + max_scroll:
                offset = scroll_pos - pause_frames
                draw.text((-offset, y), times_str, font=smallFont, fill=secondaryColour)
            else:
                draw.text((-max_scroll, y), times_str, font=smallFont, fill=secondaryColour)

        y += 6

    draw.text((matrix.width - 4 * 3, matrix.height - 5), f"{page + 1}/{total_pages}", font=smallFont, fill=rainColour)

    return image


def showLink():
    url = f"https://dash.rubenp.com/addBoard/{BOARD_ID}"

    qr = qrcode.QRCode(
        version=None,  # Let qrcode choose best version automatically
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=0
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Generate the raw (unscaled) QR image
    qr_img = qr.make_image(fill_color="white", back_color="black").convert('RGB')

    # Determine matrix size
    width, height = matrix.width, matrix.height

    # Create blank background image (black)
    background = Image.new('RGB', (width, height), (0, 0, 0))

    # Center the QR code on the background
    background.paste(qr_img, (0,7))

    draw = ImageDraw.Draw(background)

    draw.text((0, 0), "To change board settings:", font=smallFont, fill=secondaryColour)

    draw.text((34, 6), "Scan QR or visit:", font=smallFont, fill=secondaryColour)

    url = url.replace("https://", "")

    chunks = [url[i:i+15] for i in range(0, len(url), 15)]
    y = 12
    for chunk in chunks:
        draw.text((34, y), chunk, font=smallFont, fill=primaryColour)
        y += 6

    return background


cached_messages = []
last_msg_fetch_time = 0

def showMessages(page=0, lines_per_page=8):
    global cached_messages, last_msg_fetch_time, force_refresh_messages

    now = time.time()
    if now - last_msg_fetch_time > 120 or not cached_messages or force_refresh_messages:
        print("Fetching messages from server...")
        try:
            response = requests.get(f"https://dash.rubenp.com/get_messages/{BOARD_ID}")
            messages_data = json.loads(response.text)['messages']
            cached_messages = messages_data
            last_msg_fetch_time = now
            force_refresh_messages = False
        except Exception as e:
            print("Error fetching messages:", e)
            messages_data = cached_messages
    else:
        print("Using cached messages...")
        messages_data = cached_messages

    image = Image.new("RGB", (matrix.width, matrix.height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    normal_width = 24
    last_line_width = 21  # reserve 3 characters for "1/2", etc.

    # Step 1: Wrap messages into lines considering word boundaries
    all_lines = []
    for message in messages_data:
        text = message['text']
        colour = message['colour']
        max_line_length = last_line_width if (len(all_lines) + 1) % lines_per_page == 0 else normal_width
        wrapped_lines = textwrap.wrap(text, width=max_line_length)
        for line in wrapped_lines:
            all_lines.append((line, colour))

    total_pages = max(1, (len(all_lines) + lines_per_page - 1) // lines_per_page)
    page = min(page, total_pages - 1)

    start = page * lines_per_page
    end = start + lines_per_page
    visible_lines = all_lines[start:end]

    # Step 2: Draw lines
    y = 0
    for i, (line, colour) in enumerate(visible_lines):
        draw.text((0, y), line, font=smallFont, fill=colour)
        y += 6

    # Step 3: Draw page number in bottom-right corner
    page_text = f"{page + 1}/{total_pages}"
    bbox = draw.textbbox((0, 0), page_text, font=smallFont)
    text_width = bbox[2] - bbox[0]

    draw.text((matrix.width - text_width, matrix.height - 6), page_text, font=smallFont, fill=rainColour)

    return image, page + 1 < total_pages


def show_board():
    global current_mode
    global client

    scroll_offset = 0
    page_counter = 0
    page = 0
    previous_mode = None

    while True:
        matrix.brightness = 100
        mode = MODES[current_mode]

        # Publish status if mode has changed
        if mode != previous_mode:
            msg = {
                "mode": mode
            }
            client.publish(f"board/{BOARD_ID}/status", json.dumps(msg))
            previous_mode = mode

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

        elif mode == "link":
            matrix.brightness = 75
            led.on()
            image = showLink()
            matrix.SetImage(image)
            update_event.wait()
            update_event.clear()

        elif mode == "messages":
            matrix.brightness = 100
            led.on()
            image, has_more = showMessages(page=page)
            matrix.SetImage(image)

            page_counter += 1
            if page_counter >= 1:
                page_counter = 0
                if has_more:
                    page += 1
                else:
                    page = 0  # back to first page

            wait_time = 15


        elif mode == "off":
            matrix.Clear()
            led.off()
            update_event.wait()
            update_event.clear()
            continue

        if update_event.wait(wait_time):
            update_event.clear()


if __name__ == '__main__':
    if check_wifi():
        print("Wi-Fi connected.")

        # Start MQTT thread
        threading.Thread(target=run_mqtt, daemon=True).start()

        # Wait for MQTT to connect
        if mqtt_connected.wait(timeout=10):
            print("MQTT connected.")
            show_board()
        else:
            print("MQTT connection timeout.")

    else:
        print("No Wi-Fi detected. Creating Access Point.")
        create_access_point()
        display_qr_code()
