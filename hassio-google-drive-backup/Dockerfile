# Use an official Python runtime as a parent image
ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3
WORKDIR /app
COPY . /app
RUN pip3 install --trusted-host pypi.python.org -r requirements.txt
EXPOSE 1627
CMD ["python3", "run.py"]