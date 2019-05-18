ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add python3
RUN apk add fping
WORKDIR /app
COPY . /app
RUN pip3 install --upgrade pip
RUN pip3 install --trusted-host pypi.python.org -r requirements.txt
EXPOSE 1627
EXPOSE 8099
ENTRYPOINT ["python3", "-m", "backup"]