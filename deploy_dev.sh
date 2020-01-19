#!/bin/bash
sudo docker run --rm --privileged \
        -v /home/stephen/.docker:/root/.docker \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v /etc/allmystuff/data/vscode/git/hassio-google-drive-backup/hassio-google-drive-backup:/data \
        homeassistant/amd64-builder --aarch64 -t /data --version dev --no-latest
