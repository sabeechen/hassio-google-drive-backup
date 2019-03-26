
echo "$PWD/hassio-google-drive-backup/"
docker build --build-arg BUILD_FROM="homeassistant/amd64-base:latest" -t "local/hassio-google-drive-backup" "hassio-google-drive-backup/"
docker run --rm -v "%~dp0/dev/data:/data" -v "%~dp0/dev/ssl:/ssl" -v "%~dp0/dev/backup:/backup" -p "1627:1627/tcp" -l "run-from-vscode=1" "local/hassio-google-drive-backup"
