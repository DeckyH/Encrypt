 
#!/usr/bin/python3

import sys
import os
import getpass
import pyAesCrypt
from hashlib import sha256

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

isHash = getpass.getpass(prompt='Do you have a hash password? Y/N: ', stream=None)

if isHash.upper() == 'Y':
    password = getpass.getpass(prompt='Enter hash password: ', stream=None)
else:
    print("OK then, let's do the quiz...")
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

    # generate a SHA256 hash of the answers (password)
    password = str(sha256(answersPreHashed.encode('utf-8')).hexdigest())


# encryption/decryption buffer size - 64K
bufferSize = 64 * 1024

directory = input('Now enter the full directory path to where your files are stored eg. /Users/john/Desktop/enc:  ') 
files = os.listdir(directory)

for file in files:
    if action == 'decrypt' and 'aes' in file and 'DS_Store' not in file:
        print("Decrypting", directory + '/' + file)
        pyAesCrypt.decryptFile(directory + "/" + file, directory + "/" + file[:-4], password, bufferSize)
    elif action == 'encrypt' and 'aes' not in file and 'enc' not in file and 'DS_Store' not in file:
        print("Encrypting", directory + '/' + file)
        pyAesCrypt.encryptFile(directory + "/" + file, directory + "/" + file + ".aes", password, bufferSize)






