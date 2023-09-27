#!/usr/bin/python3

import os
import sys
from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit, QMessageBox

class FileCryptGUI(QWidget):

    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):

        layout = QVBoxLayout()

        self.password_label = QLabel("Enter encryption password:")
        layout.addWidget(self.password_label)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        self.salt_label = QLabel("Enter salt:")
        layout.addWidget(self.salt_label)
        self.salt_input = QLineEdit()
        self.salt_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.salt_input)

        self.file_label = QLabel("File to process:")
        layout.addWidget(self.file_label)
        self.file_input = QLineEdit()
        layout.addWidget(self.file_input)

        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_file)
        layout.addWidget(self.browse_button)

        self.encrypt_button = QPushButton("Encrypt")
        self.encrypt_button.clicked.connect(self.encrypt_file)
        layout.addWidget(self.encrypt_button)

        self.decrypt_button = QPushButton("Decrypt")
        self.decrypt_button.clicked.connect(self.decrypt_file)
        layout.addWidget(self.decrypt_button)

        self.setLayout(layout)

        self.setWindowTitle("FileCrypt GUI")
        self.setGeometry(300, 300, 400, 400)
        self.show()

    def pad(self, s):
        return s + b"\0" * (AES.block_size - len(s) % AES.block_size)

    def get_private_key(self, password, salt):
        salt = bytes(salt, "utf-8")
        kdf = PBKDF2(password, salt, 64, 1000)
        key = kdf[:32]
        return key

    def encrypt_message(self, message, key, key_size=256):
        message = self.pad(message)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return iv + cipher.encrypt(message)

    def decrypt_message(self, ciphertext, key):
        iv = ciphertext[:AES.block_size]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = cipher.decrypt(ciphertext[AES.block_size:])
        return plaintext.rstrip(b"\0")

    def browse_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select File")
        self.file_input.setText(file)

    def encrypt_file(self):
        password = self.password_input.text()
        salt = self.salt_input.text()
        file = self.file_input.text()

        if not password or not salt or not file:
            QMessageBox.warning(self, "Warning", "Please fill in all fields.")
            return

        key = self.get_private_key(password, salt)
        
        try:
            with open(file, 'rb') as fo:
                plaintext = fo.read()
            enc = self.encrypt_message(plaintext, key)
            with open(file + ".enc", 'wb') as fo:
                fo.write(enc)
            QMessageBox.information(self, "Success", "File encrypted successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def decrypt_file(self):
        password = self.password_input.text()
        salt = self.salt_input.text()
        file = self.file_input.text()

        if not password or not salt or not file:
            QMessageBox.warning(self, "Warning", "Please fill in all fields.")
            return

        key = self.get_private_key(password, salt)

        try:
            with open(file, 'rb') as fo:
                ciphertext = fo.read()
            dec = self.decrypt_message(ciphertext, key)
            output_file = os.path.splitext(file)[0]
            with open(output_file, 'wb') as fo:
                fo.write(dec)
            QMessageBox.information(self, "Success", "File decrypted successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    file_crypt_gui = FileCryptGUI()
    sys.exit(app.exec_())

