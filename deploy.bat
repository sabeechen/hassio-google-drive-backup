set /p test_input= This will publish a new version of the add-on to Docker Hub.  Type 'deploy' to make sure you aren't doing this on accident:  
if "%test_input%" NEQ "deploy" exit
set /p v= Please enter the version number exactly as it appears in config.json:  
echo Version is: %v%
@echo off
for %%p in (armhf armv7 aarch64 amd64 i386) do (
	docker build --pull -t "sabeechen/hassio-google-drive-backup-%%p:%v%" --label "io.hass.version=%v%" --build-arg "BUILD_FROM=homeassistant/%%p-base:latest" --build-arg "BUILD_VERSION=%v%" --label "io.hass.arch=%%p" --build-arg "BUILD_ARCH=%%p" hassio-google-drive-backup/
	docker tag "sabeechen/hassio-google-drive-backup-%%p:%v%" "sabeechen/hassio-google-drive-backup-%%p:latest"
	docker push "sabeechen/hassio-google-drive-backup-%%p:%v%"
	docker push "sabeechen/hassio-google-drive-backup-%%p:latest"
	echo Finished %%p
	echo.
)
exit 0
