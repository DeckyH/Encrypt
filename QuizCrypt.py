#!/usr/bin/python3

import os
import sys
import getpass
from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from hashlib import sha256

# AES helper functions
def pad(s):
    return s + b"\0" * (AES.block_size - len(s) % AES.block_size)

def get_private_key(password, salt):
    salt = bytes(salt, "utf-8")
    kdf = PBKDF2(password, salt, 64, 1000)
    key = kdf[:32]
    return key

def encrypt(message, key, key_size=256):
    message = pad(message)
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return iv + cipher.encrypt(message)

def decrypt(ciphertext, key):
    iv = ciphertext[:AES.block_size]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext[AES.block_size:])
    return plaintext.rstrip(b"\0")

def encrypt_file(file_name, key):
    with open(file_name, 'rb') as fo:
        plaintext = fo.read()
    enc = encrypt(plaintext, key)
    with open(file_name + ".enc", 'wb') as fo:
        fo.write(enc)

def decrypt_file(file_name, key):
    with open(file_name, 'rb') as fo:
        ciphertext = fo.read()
    dec = decrypt(ciphertext, key)
    with open(file_name[:-4], 'wb') as fo:
        fo.write(dec)

# End AES helper functions

def welcome():
    print("#####################################################")
    print("#                                                   #")
    print("#            Welcome to QuizCrypt!!                 #")
    print("#                                                   #")
    print("#####################################################")

welcome()

# check command line argument
argChoices = ['encrypt', 'decrypt']

if len(sys.argv) != 2:
    raise ValueError("Please specify argument 'encrypt' or 'decrypt'")
elif sys.argv[1] not in argChoices:
    raise ValueError("Please specify argument 'encrypt' or 'decrypt'")

action = sys.argv[1]

# Quiz to regenerate key

answersRaw = []
answersPreHashed = ''

# salt for use in key generation, it's fine to hard code as key will be unique
salt = 'anyrandomtextT2YpnRLAKWc86My1234'

q1 = getpass.getpass(prompt='Please type the answer to Question 1 (no spaces, all lower case): ', stream=None) 
answersRaw.append(q1)
q2 = getpass.getpass(prompt='Please type the answer to Question 2 (no spaces, all lower case): ', stream=None) 
answersRaw.append(q2)
q3 = getpass.getpass(prompt='Please type the answer to Question 3 (no spaces, all lower case): ', stream=None) 
answersRaw.append(q3)
q4 = getpass.getpass(prompt='Please type the answer to Question 4 (no spaces, all lower case): ', stream=None) 
answersRaw.append(q4)
q5 = getpass.getpass(prompt='Please type the answer to Question 5 (no spaces, all lower case): ', stream=None) 
answersRaw.append(q5)

# concat answers
for answer in answersRaw:
    answersPreHashed += answer

# generate a SHA256 hash of the answers
answersHashed = str(sha256(answersPreHashed.encode('utf-8')).hexdigest())

# generate key to unlock document(s)
key = get_private_key(answersHashed, salt)

# get directory containing encrypted files
directory = input("Now enter the full directory path to where your files are stored eg. /Users/john/Desktop/enc: ")
files = os.listdir(directory)

# loop through files in the directory and decrypt
for file in files:
    if action == 'decrypt' and 'enc' in file and 'DS_Store' not in file:
        print("Decrypting", directory + '/' + file)
        decrypt_file(directory + '/' + file, key)
    elif action == 'encrypt' and 'enc' not in file:
        print("Encrypting", directory + '/' + file)
        encrypt_file(directory + '/' + file, key)

print("All files {0}ed".format(action))
    






