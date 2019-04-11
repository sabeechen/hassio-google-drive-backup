#!/usr/bin/python3.7
import os

if __name__ == '__main__':
    os.system("docker build --build-arg BUILD_FROM=\"homeassistant/amd64-base:latest\" -t \"local/hassio-google-drive-backup\" \"hassio-google-drive-backup/\"")
    os.system("docker run --rm -v \"$(pwd)\"/dev/data:/data -v \"$(pwd)\"/dev/ssl:/ssl -v \"$(pwd)\"/dev/backup:/backup -p \"1627:1627/tcp\" -l \"run-from-vscode=1\" \"local/hassio-google-drive-backup\"")
