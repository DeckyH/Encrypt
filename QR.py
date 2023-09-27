import pyqrcode 
from pyqrcode import QRCode 
  
# String which represent the QR code 
s = """https://www.youtube.com/watch?v=vNwYtllyt3Q"""
  
# Generate QR code 
url = pyqrcode.create(s) 
  
# Create and save the png file naming "myqr.png" 
url.svg("/Users/decky/Desktop/QR/BrianEno_MusicForAirports.svg", scale = 8) 