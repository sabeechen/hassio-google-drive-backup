import getpass
import subprocess
import os
import json
from os.path import abspath, join

with open(abspath(join(__file__, "..", "..", "config.json"))) as f:
    version = json.load(f)["version"]

try:
    p = getpass.getpass("Enter DockerHub Password")
except Exception as error:
    print('ERROR', error)
    exit()

os.chdir("hassio-google-drive-backup")
print("Setting the appropriate gcloud project...")
subprocess.run("gcloud config set project hassio-drive-backup", shell=True)
print("Building and uploading dev container...")
subprocess.run("gcloud builds submit --config cloudbuild-dev.yaml --substitutions _DOCKERHUB_PASSWORD={0},_VERSION={1}".format(p, version), shell=True)
