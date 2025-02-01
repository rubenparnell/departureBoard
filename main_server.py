from flask import Flask, request, render_template_string
import json

app = Flask(__name__)

# Default station settings (same as in your departure board script)
station1 = "TYN"
platform1 = 1

station2 = "TYN"
platform2 = 2

# HTML template for a simple settings page
html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Departure Board Settings</title>
</head>
<body>
    <h1>Change Station and Platform</h1>
    <form method="POST">
        <label>Station 1:</label>
        <input type="text" name="station1" value="{{ station1 }}" required><br>

        <label>Platform 1:</label>
        <input type="number" name="platform1" value="{{ platform1 }}" required><br>

        <label>Station 2:</label>
        <input type="text" name="station2" value="{{ station2 }}" required><br>

        <label>Platform 2:</label>
        <input type="number" name="platform2" value="{{ platform2 }}" required><br>

        <button type="submit">Save</button>
    </form>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    global station1, platform1, station2, platform2

    if request.method == "POST":
        station1 = request.form["station1"]
        platform1 = int(request.form["platform1"])
        station2 = request.form["station2"]
        platform2 = int(request.form["platform2"])

        # Save the settings to a JSON file
        with open("settings.json", "w") as f:
            json.dump({"station1": station1, "platform1": platform1, 
                       "station2": station2, "platform2": platform2}, f)

    return render_template_string(html_template, station1=station1, platform1=platform1, 
                                  station2=station2, platform2=platform2)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
