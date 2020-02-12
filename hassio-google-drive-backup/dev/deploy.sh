#!/bin/bash
sudo docker run --rm --privileged \
        -v /home/coder/.docker:/root/.docker \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v ..:/data \
        homeassistant/amd64-builder --all -t /data