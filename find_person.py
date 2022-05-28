#!/usr/bin/python3
# Created By: Srinath Venkatraman
# Description: Python Script uses Azure FaceAPI to detect and verify faces.
import os
import time
import re
import argparse
from tkinter import Image
import colorama
import shutil
import http.client, urllib, base64
from config import config
from pathlib import Path
from azure.cognitiveservices.vision.face import FaceClient
from msrest.authentication import CognitiveServicesCredentials
from azure.cognitiveservices.vision.face.models._models_py3 import APIErrorException
from flask import Flask, flash, request, redirect, render_template, url_for, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont

KEY = config["KEY"]
ENDPOINT = config["ENDPOINT"]
MAX_REQUEST_RATE = config["MAX_REQUEST"]
REQUEST_TIMEOUT_TIME = config["REQUEST_TIMEOUT_TIME"]
accepted_extensions = ["jpg", "png", "jpeg", "bmp", "webp", "gif"]
global intRequestCounter
intRequestCounter = 0
global intTotalRequests
intTotalRequests = 0
global intFileIndex
intFileIndex = 0
global intSuccessMatches
intSuccessMatches = 0
global dirFoundImages
dirFoundImages = './static/Found'
global personList
personList = []
global image_counter
image_counter = 0

base = './'
fi = [str(f) for f in os.listdir(base)]
for f in fi:
  if '.' not in f and f != 'static' and f != 'templates' and f != '__pycache__':
    personList.append(f)


headers = {
    # Request headers
    'Ocp-Apim-Subscription-Key': KEY
}

params = urllib.parse.urlencode({
    # Request parameters
    'top': '1000',
    'returnRecognitionModel': 'false',
})

conn = http.client.HTTPSConnection('centralindia.api.cognitive.microsoft.com')
conn.request("GET", "https://srinathv.cognitiveservices.azure.com/face/v1.0/persongroups?%s" % params, "{body}", headers)
response = conn.getresponse()
data = response.read()
print('these should be the names of personList {}'.format(data))
conn.close()

colorama.init()
face_client = FaceClient(ENDPOINT, CognitiveServicesCredentials(KEY))

parser = argparse.ArgumentParser(description='Find face matches from one image.')
parser.add_argument('--detection-model', dest='detection_model', type=str,
                    default='detection_03',
                    help='detection model for Microsoft Azure. Default is detection_03')
parser.add_argument('--recognition-model', dest='recognition_model', type=str,
                    default='recognition_04',
                    help='recognition model for Microsoft Azure. Default is recognition_04')
parser.add_argument('--max', dest='max_request_limit', type=int,
                    help='Do you want the program to stop at a certain threshold? Ex: 100000 requests')
args = parser.parse_args()

Path(dirFoundImages).mkdir(parents=True, exist_ok=True)


def getImageFilesFromDirectory(upload_folder):
  arPossibleImages = [fn for fn in os.listdir(upload_folder) if fn.split(".")[-1] in accepted_extensions]
  if (intFileIndex != 0):
    arPossibleImages = arPossibleImages[intFileIndex:len(arPossibleImages)]
  return arPossibleImages

def openTargetFile(check_image):
  try: 
    return open(check_image, 'rb') 
  except:
    exit('Cannot open the target image file: '+ check_image)

def calculateAPIErrorTimeout(errorMessage):
  querySecond = re.search('after (.*) second', errorMessage)
  if (querySecond != None):
    return int(querySecond.group(1)) + 1
  return 1
  
def checkMaxRequestLimit():
    global intTotalRequests
    intTotalRequests += 1
    if (args.max_request_limit != None):
        if (intTotalRequests > args.max_request_limit):
          print('Max Request Limit has been reached. Total Requests: ' + str(intTotalRequests))
          exit('Limit Set By User: ' + str(args.max_request_limit))


def runSleepForMaxRequest():
    global intRequestCounter
    if (intRequestCounter >= MAX_REQUEST_RATE):
      print('MAX REQUEST RATE ACHIEVED. STALL {} SECONDS.'.format(REQUEST_TIMEOUT_TIME+6))
      time.sleep(REQUEST_TIMEOUT_TIME+6)
      intRequestCounter = 0


def comparePersonGroupToFace(possibleDetectedFace, imgPossibleName, f_name, upload_folder):
  arPersonResults = face_client.face.identify([possibleDetectedFace.face_id], f_name)
  if not arPersonResults:
    print('No person identified in the person group for faces from {}.'.format(imgPossibleName))
  for person in arPersonResults:
    if len(person.candidates) > 0:
      print('Person for face ID {} is identified in {} with a confidence of {}.'.format(person.face_id, imgPossibleName, person.candidates[0].confidence))
      global intSuccessMatches
      intSuccessMatches += 1
      shutil.copyfile(os.path.join(upload_folder, imgPossibleName), os.path.join(dirFoundImages, imgPossibleName))
    else:
      print('No person identified in {}.'.format(imgPossibleName))

def getPossibleDetectedFaces(imageName, upload_folder):
  imgPossible = open(os.path.join(upload_folder, imageName), 'rb') 
  arPossibleDetectedFaces = face_client.face.detect_with_stream(imgPossible, detection_model=args.detection_model, recognition_model=args.recognition_model)
  print('{} face(s) detected from image {}.'.format(len(arPossibleDetectedFaces), imageName))
  return arPossibleDetectedFaces


def getTargetImageFaceId(check_image):
  targetImage = openTargetFile(check_image)
  targetImageName = os.path.basename(targetImage.name)
  arDetectedFaces = face_client.face.detect_with_stream(targetImage, detection_model=args.detection_model, recognition_model=args.recognition_model)
  targetImageFaceIDs = []
  targetImagerect = {}
  for DetectedFaces in arDetectedFaces:
     targetImageFaceIDs.append(DetectedFaces.face_id)
     targetImagerect['{}'.format(str(DetectedFaces.face_id))] = DetectedFaces.face_rectangle

  print('{} face detected from target image {}.'.format(len(arDetectedFaces), targetImageName))
  return targetImageFaceIDs, targetImageName, targetImagerect

def getAPIExceptionAction(errorMessage):
  print(errorMessage.message)
  if (errorMessage.message == '(InvalidImage) Resizing image failed, image format not supported.'):
    global intFileIndex
    intFileIndex += 1
  intTimeToSleep = calculateAPIErrorTimeout(errorMessage.message)
  print('File Index is at: {}'.format(intFileIndex))
  print('Pausing and Resuming in {} seconds...'.format(intTimeToSleep))
  args.start_at = intFileIndex
  time.sleep(intTimeToSleep)

def check_person(check_image):
  targetImageFaceIDs, targetImageName, targetImagerect = getTargetImageFaceId(check_image)
  global intSuccessMatches
  for person in personList:
    arPersonResults = face_client.face.identify(face_ids = targetImageFaceIDs, person_group_id = person)
    if not arPersonResults:
      print('No person identified in the person group for faces from {}.'.format(targetImageName))
    for people in arPersonResults:
      if len(people.candidates) > 0:
        print('Person for face ID {} is identified in {} with a confidence of {}.'.format(people.face_id, person, people.candidates[0].confidence))
        intSuccessMatches += 1
        global image_counter
        image_counter += 1
        img = Image.open(check_image)
        draw = ImageDraw.Draw(img)
        rect = targetImagerect['{}'.format(str(people.face_id))]
        left = rect.left
        top = rect.top
        right = rect.width + left
        bottom = rect.height + top
        draw.rectangle(((left,top),(right,bottom)), outline = 'green', width = 5)
        draw.text((left,bottom), "{}".format(str(person)), fill=(0,255,0))
        path = './static/results'
        img.save('static/results/{}_{}.png'.format(str(person),str(image_counter)),'PNG')
        shutil.copyfile(check_image, os.path.join(dirFoundImages, targetImageName))
      else:
        print('No person identified in {}.'.format(person))

def find_func(upload_folder, f_name):
  arImageFiles = getImageFilesFromDirectory(upload_folder)
  print('Total Images in Processing: {}'.format(len(arImageFiles)))
  endLoop = True
  while (endLoop == True):
    try:
      for imageName in getImageFilesFromDirectory(upload_folder):
        arPossibleDetectedFaces = getPossibleDetectedFaces(imageName,upload_folder)
        for possibleDetectedFace in arPossibleDetectedFaces:
          comparePersonGroupToFace(possibleDetectedFace, imageName, f_name, upload_folder)
      endLoop = False
      print('{} Images Processed'.format(len(arImageFiles)))
    except APIErrorException as errorMessage:
      getAPIExceptionAction(errorMessage)
      intRequestCounter = 0
    

app=Flask(__name__)

app.secret_key = "secret key"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Allowed extension you can set your own
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload/<filename>')
def send_image(filename):
    return redirect(url_for('static', filename = 'Found/'+ filename), code = 301)

@app.route('/check-result/<filename>')
def check_result(filename):
  return redirect(url_for('static', filename = 'results/'+ filename), code = 301)

@app.route('/check')
def check_criminal():
  return render_template('indexCheck_HH.html')

@app.route('/check', methods=['POST'])
def check_crim_func():
  if request.method =='POST':
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    file = request.files['file']
    path = os.getcwd()
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        check_image=os.path.join(path, filename)
        file.save(check_image)
        flash('File successfully uploaded')
        path = os.getcwd()
        if os.path.isdir('./static/results'):
           shutil.rmtree(os.path.join(path, '{}'.format('static/results')))
        upload_folder = os.path.join(path, '{}'.format('static/results'))
        # Make directory if uploads is not exists
        os.mkdir(upload_folder)
        check_person(check_image)
        os.remove(check_image)
    base_path = './static/results'
    file_ls = [f for f in os.listdir(base_path)]
    return render_template('indexCheck_HH.html', filenames = file_ls )

@app.route('/find')
def find_person():
  return render_template('indexFindOption.html')

@app.route('/find', methods=['POST'])
def finder():
  if request.method == 'POST':

    f_name = request.form['name']
    if 'files[]' not in request.files:
            flash('No file part')
            return redirect(request.url)

    files = request.files.getlist('files[]')
    path = os.getcwd()
     # file Upload
    upload_folder = os.path.join(path, 'finder')
    # Make directory if uploads is not exists
    if not os.path.isdir(upload_folder):
        os.mkdir(upload_folder)

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(upload_folder, filename))
    
    flash('File(s) successfully uploaded')
    if os.path.isdir('./static/Found'):
        shutil.rmtree(os.path.join(path, 'static/Found'))
    os.mkdir(os.path.join(path,'static/Found'))
    find_func(upload_folder, f_name)
    path = os.getcwd()
    shutil.rmtree(os.path.join(path, 'finder'))
    image_names = os.listdir('./static/Found')
    return render_template('indexFindOption.html',filenames=image_names)

@app.route('/')
def choose_option_HH():
    return render_template('indexOption_HH.html')

@app.route('/', methods=['POST'])
def indexOption_HH():
    if request.method == 'POST':
        if request.form.get('action1') == 'CHECK FOR CRIMINALS':
            return redirect(url_for('check_criminal'))
        elif request.form.get('action2') == 'FIND CRIMINAL':
            return redirect(url_for('find_person'))

if __name__ == "__main__":
    app.run(debug=False,port=5013)
    