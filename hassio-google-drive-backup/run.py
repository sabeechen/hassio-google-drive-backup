#!/usr/bin/env python3

import sys
import logging

from backup.server import Server
from backup.engine import Engine
from backup.config import Config
from backup.drive import Drive
from backup.hassio import Hassio
from backup.time import Time
from backup.watcher import Watcher
from threading import Thread
from time import sleep
from backup.config import HASSIO_OPTIONS_FILE
from backup.logbase import LogBase


def main() -> None:
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

    time: Time = Time()

    if len(sys.argv) == 1:
        config: Config = Config([HASSIO_OPTIONS_FILE])
    else:
        config: Config = Config(sys.argv[1:])

    hassio: Hassio = Hassio(config)
    while True:
        try:
            hassio.loadInfo()
            break
        except Exception:
            LogBase().critical("Unable to reach Hassio supervisor.  Please ensure the supervisor is running.")
            sleep(10)

    if config.warnIngress():
        LogBase().warn("This add-on supports ingress but your verison of Home Assistant does not.  Please update to the latest verison of home Assistant.")

    drive: Drive = Drive(config)
    try:
        watcher: Watcher = Watcher(time, config)
        engine: engine = Engine(watcher, config, drive, hassio, time)  # type: ignore
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
    finally:
        if watcher:
            watcher.stop()


if __name__ == '__main__':
    main()
