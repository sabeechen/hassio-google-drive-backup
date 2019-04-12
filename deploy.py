#!/usr/bin/python3.7
import os
import json
import docker
from typing import Dict, Any, List


def main() -> None:
    version: str = ""
    with open("hassio-google-drive-backup/config.json") as file:
        config: Dict[str, Any] = json.load(file)
        version = config['version']
    answer: str = input("This will deploy version " + version + " of the add-on to docker hub.  Type DEPLOY in all caps to continue or enter a different version lable to use for testing:")
    if len(answer) == 0:
        print("Quitting")
        return

    if answer == 'DEPLOY':
        print("Publishing version " + version)
    else:
        version = answer
        print("Publishing test version " + version)

    os.system("docker login")

    client = docker.from_env()
    platforms: List[str] = ["armhf", "armv7", "aarch64", "amd64", "i386"]
    for platform in platforms:
        tag_platform = "sabeechen/hassio-google-drive-backup-{0}:{1}".format(platform, version)
        tag_latest = "sabeechen/hassio-google-drive-backup-{0}:latest".format(platform)
        print("Building " + tag_platform)
        client.images.build(
            path="hassio-google-drive-backup",
            tag=tag_platform,
            pull=True,
            labels={
                "io.hass.version": version,
                "io.hass.arch": platform,
            },
            buildargs={
                "BUILD_FROM": "homeassistant/{0}-base:latest".format(platform),
                "BUILD_VERSION": version,
                "BUILD_ARCH": platform
            }
        )

        print("Building " + tag_latest)
        client.images.build(
            path="hassio-google-drive-backup",
            tag=tag_latest,
            pull=True,
            labels={
                "io.hass.version": version,
                "io.hass.arch": platform,
            },
            buildargs={
                "BUILD_FROM": "homeassistant/{0}-base:latest".format(platform),
                "BUILD_VERSION": version,
                "BUILD_ARCH": platform
            }
        )

        print("Pushing " + tag_platform)
        for line in client.images.push(tag_platform, stream=True, decode=True):
            print(line)

        print("Pushing " + tag_latest)
        for line in client.images.push(tag_latest, stream=True, decode=True):
            print(line)

        """
        #print("Tagging sabeechen/hassio-google-drive-backup-{0}:{1}".format(platform, version))
        #build = 'docker build --pull -t "sabeechen/hassio-google-drive-backup-{0}:{1}" --label "io.hass.version={1}" --build-arg "BUILD_FROM=homeassistant/{0}-base:latest" --build-arg "BUILD_VERSION={1}" --label "io.hass.arch={0}" --build-arg "BUILD_ARCH={0}" hassio-google-drive-backup/'.format(platform, version)
        tag = 'docker tag "sabeechen/hassio-google-drive-backup-{0}:{1}" "sabeechen/hassio-google-drive-backup-{0}:latest"'.format(platform, version)
        push1 = 'docker push "sabeechen/hassio-google-drive-backup-{0}:{1}"'.format(platform, version)
        push2 = 'docker push "sabeechen/hassio-google-drive-backup-{0}:latest"'.format(platform)
        #os.system(build)
        #os.system(tag)
        #os.system(push1)
        #os.system(push2)
        """


if __name__ == '__main__':
    main()
