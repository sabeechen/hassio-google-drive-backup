#!/usr/bin/python3.7
import docker  # type: ignore
from typing import List


def main() -> None:
    version: str = "devtesting"
    client = docker.from_env()
    platforms: List[str] = ["armv7"]
    for platform in platforms:
        tag_platform = "sabeechen/hassio-google-drive-backup-{0}:{1}".format(platform, version)
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

        print("Pushing " + tag_platform)
        for line in client.images.push(tag_platform, stream=True, decode=True):
            print(line)


if __name__ == '__main__':
    main()
