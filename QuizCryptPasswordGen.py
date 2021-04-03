#!/usr/bin/python3

import os
import sys
import getpass
from hashlib import sha256

answersRaw = []
answersPreHashed = ''

print("This app will generate a hash password you can use to encrypt or decrypt your files. Please store it safely once created. ")
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

# generate a SHA256 hash of the answers
answersHashed = str(sha256(answersPreHashed.encode('utf-8')).hexdigest())
print("Please store the following hash in a safe place: ", answersHashed)

