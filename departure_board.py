import time
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image, ImageDraw, ImageFont
import requests
import json

# Load station settings from JSON file
try:
    with open("settings.json", "r") as f:
        settings = json.load(f)
        station1 = settings["station1"]
        platform1 = settings["platform1"]
        station2 = settings["station2"]
        platform2 = settings["platform2"]
except FileNotFoundError:
    print("Settings file not found, using defaults.")


# Configuration for the matrix
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

# Set up text settings
font_path = "./5x8.bdf"
font_size = 8  # Adjust font size if needed
font = ImageFont.truetype(font_path, font_size)

smallFontHeight = 6
smallFont = ImageFont.truetype("./4x6.bdf", smallFontHeight)

destinationColour = (246, 115, 25)
stationColour = (6, 234, 49)

#Get station name:
stations = json.loads(requests.get(f"https://metro-rti.nexus.org.uk/api/stations").text)
station1Name = stations[station1]
station2Name = stations[station2]


def getTrains(stationCode, platform):
  try:
 #   logging.info("fetching")
    data = requests.get(f"https://metro-rti.nexus.org.uk/api/times/{stationCode}/{platform}")
    return json.loads(data.text)
  except:
    ()
 #   logging.error("error fetching")


def getButton():
  with open("/home/ruben/button/toggle_file.txt", "r+") as f:
    # Read the first line and strip any newline or whitespace
    line = str(f.readline().strip())

    # Convert to integer (or leave as a string, depending on your use case)
    show = True if line == "1" else False
  return show


allTrains1 = []
trains = getTrains(station1, platform1)[:2]
for train in trains:
    allTrains1.append((train['destination'], train['dueIn']))

allTrains2 = []
trains = getTrains(station2, platform2)[:2]
for train in trains:
    allTrains2.append((train['destination'], train['dueIn']))

#print("loaded")
while True:
    current_time = int(time.time())

    show = getButton()

    if show:
        lowestPixel = 1
        # Clear screen:
        image = Image.new("RGB", (matrix.width, matrix.height), (0,0,0))
        draw = ImageDraw.Draw(image)

        if current_time % 30 == 0:
            #print("loading...")
            # Get train data
            allTrains1 = []
            trains = getTrains(station1, platform1)[:2]
            for train in trains:
                allTrains1.append((train['destination'], train['dueIn']))

            allTrains2 = []
            trains = getTrains(station2, platform2)[:2]
            for train in trains:
                allTrains2.append((train['destination'], train['dueIn']))


        # Display 1st info
        draw.text((1, lowestPixel), f"{station1Name}: {platform1}", font=smallFont, fill=stationColour)
        lowestPixel += smallFontHeight

        for i, train in enumerate(allTrains1):
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
            
        if len(allTrains1) == 0:
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
        draw.text((1, lowestPixel), f"{station2Name}: {platform2}", font=smallFont, fill=stationColour)
        lowestPixel += smallFontHeight

        for i, train in enumerate(allTrains2):
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

        if len(allTrains1) == 0:
            lowestPixel += 2
            text = "There are no services"
            draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=destinationColour)
            lowestPixel += smallFontHeight+1

            text = "from this platform"
            draw.text((int(matrix.width/2-(len(text)*4/2)), lowestPixel), text, font=smallFont, fill=destinationColour)

        # Display the image
        matrix.SetImage(image.convert('RGB'))
    else:
        #print("show is false")
        image = Image.new("RGB", (matrix.width, matrix.height), (0,0,0))
        draw = ImageDraw.Draw(image)
        matrix.SetImage(image.convert('RGB'))


    time.sleep(1)
