ARG BUILD_FROM
FROM $BUILD_FROM
WORKDIR /app
COPY . /app
RUN chmod +x addon_deps.sh
RUN ./addon_deps.sh
RUN pip3 install .
COPY config.json /usr/local/lib/python3.8/site-packages/config.json

EXPOSE 1627
EXPOSE 8099
ENTRYPOINT ["python3", "-m", "backup"]