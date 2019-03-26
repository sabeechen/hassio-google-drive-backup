#!/bin/bash
PLATFORMS="armhf armv7 aarch64 amd64 i386"


read -p "Enter version number, ensuring it matches with the current config.json:"  VERSION
echo "Version: $VERSION"
# Iterate the string variable using for loop
for platform in $PLATFORMS; do
	docker build --pull -t "sabeechen/hassio-google-drive-backup-$platform:$VERSION" \
		 --label "io.hass.version=$VERSION" --build-arg "BUILD_FROM=homeassistant/armv7-base:latest" --build-arg "BUILD_VERSION=$VERSION" --label "io.hass.arch=$platform" --build-arg "BUILD_ARCH=$platform" ./hassio-google-drive-backup/
    docker tag "sabeechen/hassio-google-drive-backup-$platform:$VERSION" "sabeechen/hassio-google-drive-backup-$platform:latest"
	docker push "sabeechen/hassio-google-drive-backup-$platform:$VERSION"
	docker push "sabeechen/hassio-google-drive-backup-$platform:latest"
    echo "$platform"
done
read -p "Deployment finished, press enter to exit"  username
exit
