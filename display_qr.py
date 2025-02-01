import qrcode
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions

def generate_qr():
    url = "http://192.168.4.1:5000"  # Local setup page
    qr = qrcode.make(url)
    qr = qr.resize((96, 48), Image.Resampling.NEAREST)
    return qr

options = RGBMatrixOptions()
options.rows = 48
options.cols = 96
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'
options.brightness = 100

matrix = RGBMatrix(options=options)

qr_image = generate_qr()
matrix.SetImage(qr_image.convert("RGB"))
