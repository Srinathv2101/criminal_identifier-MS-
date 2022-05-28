#!/usr/bin/python3
# Created By: Srinath Venkatraman
# Description: Script creates one person object for Microsoft Azure FaceAPI
import os
import argparse
import time
import re
import shutil
from config import config
from termcolor import colored
from azure.cognitiveservices.vision.face import FaceClient
from msrest.authentication import CognitiveServicesCredentials
from azure.cognitiveservices.vision.face.models import TrainingStatusType, Person, QualityForRecognition, PersonGroup
from azure.cognitiveservices.vision.face.models._models_py3 import APIErrorException
from msrest.exceptions import ValidationError
from flask import Flask, flash, request, redirect, render_template, url_for
from werkzeug.utils import secure_filename

KEY = config["KEY"]
ENDPOINT = config["ENDPOINT"]
MAX_REQUEST_RATE_FREE = config["MAX_REQUEST"]
REQUEST_TIMEOUT_TIME = config["REQUEST_TIMEOUT_TIME"]
face_client = FaceClient(ENDPOINT, CognitiveServicesCredentials(KEY))
accepted_extensions = ["jpg", "png", "jpeg", "bmp", "webp", "gif"]
global intFileIndex
intFileIndex = 0
global intRequestCounter
intRequestCounter = 0

parser = argparse.ArgumentParser(description='Find face matches from one image.')
parser.add_argument('--detection-model', dest='detection_model', type=str,
                    default='detection_03',
                    help='detection model for Microsoft Azure. Default is detection_03')
parser.add_argument('--recognition-model', dest='recognition_model', type=str,
                    default='recognition_04',
                    help='recognition model for Microsoft Azure. Default is recognition_04')
args = parser.parse_args()




def getImageFilesFromDirectory(upload_folder):
  arPossibleImages = [fn for fn in os.listdir(upload_folder) if fn.split(".")[-1] in accepted_extensions]
  if (intFileIndex != 0):
    arPossibleImages = arPossibleImages[intFileIndex:len(arPossibleImages)]
  return arPossibleImages

def createPersonGroup(name):
  try:
    face_client.person_group.create(person_group_id=name, name=name, recognition_model=args.recognition_model)
    print(colored('PersonGroup Created.', 'green'))
  except ValidationError as validationError:
      exit(colored('Error for PersonGroup Name Field: {}'.format(validationError), 'red'))
  except APIErrorException as apiError:
      exit(colored(apiError.message + ' Use the -d delete option to delete existing PersonGroup and create new one.', 'red'))

def deletePersonGroup(name):
  try:
    face_client.person_group.delete(name)
    print('{} person group deleted.'.format(name))
  except ValidationError as validationError:
      exit(colored('Error for PersonGroup Name Field: {}'.format(validationError), 'red'))


def calculateAPIErrorTimeout(errorMessage):
  querySecond = re.search('after (.*) second', errorMessage)
  if (querySecond != None):
    return int(querySecond.group(1)) + 1
  return 20

def getAPIExceptionAction(errorMessage):
  print(errorMessage.message)
  intTimeToSleep = calculateAPIErrorTimeout(errorMessage.message)
  print(colored('File Index is at: {}'.format(intFileIndex), 'yellow'))
  print(colored('Pausing and Resuming in {} seconds...'.format(intTimeToSleep), 'yellow'))
  time.sleep(intTimeToSleep)

def delete_folder(name):
  path = os.getcwd()
  shutil.rmtree(os.path.join(path, '{}'.format(name)))
  print("folder {} has been deleted".format(name))

def create_func(name, upload_folder):
  print('Person group:', name)
  createPersonGroup(name)
  person = face_client.person_group_person.create(name, name, name)

  endLoop = False
  while (endLoop == False):
    try:
      for imageName in getImageFilesFromDirectory(upload_folder):
        imagePerson = open(os.path.join(upload_folder, imageName), 'r+b')
        sufficientQuality = True
        detected_faces = face_client.face.detect_with_stream(imagePerson, detection_model=args.detection_model, recognition_model=args.recognition_model, return_face_attributes=['qualityForRecognition'])
        face_client.person_group_person.add_face_from_stream(name, person.person_id, open(os.path.join(upload_folder, imageName), 'r+b'), detection_model=args.detection_model)
        print('Image {} added to Person Object: {}'.format(imageName, name))
        ##incrementCounter()     
      endLoop = True
    except APIErrorException as errorMessage:
      getAPIExceptionAction(errorMessage)
  
  print('Training the PersonGroup...')
  face_client.person_group.train(name)
  while (True):
      training_status = face_client.person_group.get_training_status(name)
      print("Training Status: {}".format(training_status.status))
      if (training_status.status is TrainingStatusType.succeeded):
          print(colored('Training Succeeded!!', 'green'))
          break
      elif (training_status.status is TrainingStatusType.failed):
          face_client.person_group.delete(person_group_id=name)
          exit(colored('Training the PersonGroup has failed.', 'red'))
      time.sleep(5)

def delete_func(name):
  deletePersonGroup(name)

app=Flask(__name__)

app.secret_key = "secret key"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Allowed extension you can set your own
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/delete')
def delete_file():
  return render_template('indexDelete.html')

@app.route('/delete', methods=['POST'])
def delete_form():
  if request.method == 'POST':

    name = request.form['name']
    delete_func(name)
    delete_folder(name)
    return render_template('indexDeleted.html')

@app.route('/create')
def upload_form():
    return render_template('indexCreate.html')

@app.route('/create', methods=['POST'])
def upload_file():
    if request.method == 'POST':

        name = request.form['name']
        if 'files[]' not in request.files:
            flash('No file part')
            return redirect(request.url)

        files = request.files.getlist('files[]')
        path = os.getcwd()
        # file Upload
        upload_folder = os.path.join(path, '{}'.format(name))

        # Make directory if uploads is not exists
        if not os.path.isdir(upload_folder):
            os.mkdir(upload_folder)

        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(upload_folder, filename))

        flash('File(s) successfully uploaded')
        create_func(name,upload_folder)

        return redirect('/create')

@app.route('/')
def choose_option():
    return render_template('indexOption.html')

@app.route('/', methods=['POST'])
def indexOption():
    if request.method == 'POST':
        if request.form.get('action1') == 'CREATE PERSON GROUP':
            return redirect(url_for('upload_form'))
        elif request.form.get('action2') == 'DELETE PERSON GROUP':
            return redirect(url_for('delete_file'))

if __name__ == "__main__":
    app.run(debug=False)
    
