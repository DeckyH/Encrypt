import pyqrcode 
from pyqrcode import QRCode 
  
# String which represent the QR code 
s = """"""
  
# Generate QR code 
url = pyqrcode.create(s) 
  
# Create and save the png file naming "myqr.png" 
url.svg("/Users/decky/Desktop/QR/3.svg", scale = 8) 