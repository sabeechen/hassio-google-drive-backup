#!/usr/bin/env python3

import sys

from backup.server import Server
from backup.engine import Engine
from backup.config import Config
from backup.drive import Drive
from backup.hassio import Hassio
from backup.time import Time
from threading import Thread


if __name__ == '__main__':
    time: Time = Time()
    config: Config = Config(sys.argv[1:])
    drive: Drive = Drive(config)
    hassio: Hassio = Hassio(config)
    engine: engine = Engine(config, drive, hassio, time)  # type: ignore
    server: Server = Server("www", engine, config)
    server_thread: Thread = Thread(target=engine.run)  # type: ignore
    server_thread.daemon = True
    server_thread.start()
    server.run()
