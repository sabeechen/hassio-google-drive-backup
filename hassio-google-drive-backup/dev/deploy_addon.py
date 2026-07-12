import subprocess
import json
from os.path import abspath, join

with open(abspath(join(__file__, "..", "..", "config.json"))) as f:
    version = json.load(f)["version"]
print("Version will be: " + version)
subprocess.run("docker login", shell=True)


# HA image-name arch -> docker buildx platform
platforms = {"amd64": "linux/amd64", "aarch64": "linux/arm64"}

for arch, platform in platforms.items():
    subprocess.run("docker buildx build --platform {2} -f Dockerfile -t sabeechen/hassio-google-drive-backup-{0}:{1} --push hassio-google-drive-backup".format(arch, version, platform), shell=True)
