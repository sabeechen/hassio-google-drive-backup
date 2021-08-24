# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.9-buster

# Copy local code to the container image.
ENV APP_HOME /server
WORKDIR $APP_HOME
COPY . ./
COPY config.json /usr/local/lib/python3.9/site-packages/config.json

# Install server python requirements
RUN pip3 install --trusted-host pypi.python.org -r requirements-server.txt
RUN pip3 install .

WORKDIR /
ENTRYPOINT ["python3", "-m", "backup.server"]