FROM python:3.9-buster

WORKDIR /usr/src/install
RUN apt-get update
RUN apt-get install fping
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt