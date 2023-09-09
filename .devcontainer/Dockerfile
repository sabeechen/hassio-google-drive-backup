FROM python:3.11-buster

WORKDIR /usr/src/install
RUN apt-get update
RUN apt-get install fping
# install gcloud api
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg  add - && apt-get update -y && apt-get install google-cloud-cli -y
      
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt