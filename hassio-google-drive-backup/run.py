#!/usr/bin/env python3

import sys
import logging

from backup.server import Server
from backup.engine import Engine
from backup.config import Config
from backup.drive import Drive
from backup.hassio import Hassio
from backup.time import Time
from threading import Thread
from time import sleep
from backup.config import HASSIO_OPTIONS_FILE


def main() -> None:
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

    time: Time = Time()

    if len(sys.argv) == 1:
        config: Config = Config([HASSIO_OPTIONS_FILE])
    else:
        config: Config = Config(sys.argv[1:])

    drive: Drive = Drive(config)
    hassio: Hassio = Hassio(config)
    engine: engine = Engine(config, drive, hassio, time)  # type: ignore
    server: Server = Server("www", engine, config)

    engine_thread: Thread = Thread(target=engine.run)  # type: ignore
    engine_thread.setName("Engine Thread")
    engine_thread.daemon = True
    engine_thread.start()

    server_thread: Thread = Thread(target=server.run)
    server_thread.daemon = True
    server_thread.setName("Server Thread")
    server_thread.start()

    while True:
        sleep(5)


if __name__ == '__main__':
    main()
