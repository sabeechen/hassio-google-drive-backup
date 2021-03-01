import subprocess
import os
import json
from os.path import abspath, join

with open(abspath(join(__file__, "..", "..", "config.json"))) as f:
    version = json.load(f)["version"]
print("Version will be: " + version)
subprocess.run("docker login", shell=True)


platforms = ["amd64", "armv7", "aarch64", "armhf", "i386"]

os.chdir("hassio-google-drive-backup")
for platform in platforms:
    subprocess.run("docker build -f Dockerfile-addon -t sabeechen/hassio-google-drive-backup-{0}:{1} --build-arg BUILD_FROM=homeassistant/{0}-base .".format(platform, version), shell=True)

for platform in platforms:
    subprocess.run("docker push sabeechen/hassio-google-drive-backup-{0}:{1}".format(platform, version), shell=True)
