FileCrypt GUI
This repository contains a Python script that provides a graphical user interface (GUI) for encrypting and decrypting files using AES encryption. The GUI is built using PyQt5.

Prerequisites
Raspberry Pi with Raspberry Pi OS installed.
Python 3.x installed.
Installation Instructions

Step 1: Update and Upgrade
First, make sure your Raspberry Pi is up to date:

sudo apt-get update
sudo apt-get upgrade


Step 2: Install Required Packages
Install the necessary packages for running the script:

sudo apt-get install python3-pyqt5 python3-venv libatlas-base-dev

Step 3: Clone the Repository
Navigate to the directory where you want to clone the repository and run:

git clone <repository-url>
cd <repository-folder>/GUI/env

Step 4: Set Up Virtual Environment
Create a virtual environment and activate it:

python3 -m venv venv
source venv/bin/activate

Step 5: Install Python Dependencies
Install the required Python packages:

pip install pycryptodome

After following the installation steps, you can run the application with the following commands:

source venv/bin/activate
python file_crypt_gui.py

Usage
Enter encryption password: Input the password to be used for encryption/decryption.
Enter salt: Input the salt for key derivation.
File to process: Browse and select the file you want to encrypt or decrypt.
Encrypt: Click to encrypt the selected file.
Decrypt: Click to decrypt the selected file.
Troubleshooting
Ensure all required packages are installed.
Verify that the virtual environment is activated before running the script.
License
This project is licensed under the MIT License. See the LICENSE file for more details.

Acknowledgements
PyQt5 for the GUI components.
PyCryptodome for the cryptographic functions.
Feel free to contribute to this project by creating issues or submitting pull requests.







