import getpass
import subprocess
import os

try:
    p = getpass.getpass("Enter DockerHub Password")
except Exception as error:
    print('ERROR', error)
    exit()

os.chdir("hassio-google-drive-backup")
print("Setting the appropriate gcloud project...")
subprocess.run("gcloud config set project hassio-drive-backup", shell=True)
print("Building and uploading addon containers container...")
subprocess.run("gcloud builds submit --config cloudbuild-addon.yaml --substitutions _DOCKERHUB_PASSWORD=" + p + ",_VERSION=" + version, shell=True)
