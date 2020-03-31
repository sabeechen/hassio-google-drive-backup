ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add python3
RUN apk add fping
RUN apk add linux-headers
RUN apk add libc-dev
RUN apk add libffi-dev
RUN apk add python3-dev
RUN apk add gcc
WORKDIR /app
COPY . /app
RUN pip3 install --upgrade pip
RUN pip3 install --trusted-host pypi.python.org -r requirements.txt

# Remvoe packages we only needed for installation
RUN apk del linux-headers libc-dev libffi-dev python3-dev gcc

EXPOSE 1627
EXPOSE 8099
ENTRYPOINT ["python3", "-m", "backup"]