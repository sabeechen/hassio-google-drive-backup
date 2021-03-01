import subprocess
import os

os.chdir("hassio-google-drive-backup")
print("Setting the appropriate gcloud project...")
subprocess.run("gcloud config set project hassio-drive-backup", shell=True)
print("Building and uploading server container...")
subprocess.run("gcloud builds submit --config cloudbuild-server.yaml", shell=True)
