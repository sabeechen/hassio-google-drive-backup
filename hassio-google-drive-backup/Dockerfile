# Use an official Python runtime as a parent image
ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3
RUN apk add fping
WORKDIR /app
COPY . /app
RUN ["chmod", "+x", "run.py"]
RUN  pip3 install --trusted-host pypi.python.org -r requirements.txt
EXPOSE 1627
EXPOSE 8099
ENTRYPOINT /app/run.py