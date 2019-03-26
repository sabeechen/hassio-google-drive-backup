import threading
import backup
import sys

from backup.server import Server
from backup.engine import Engine
from backup.config import Config


if __name__ == '__main__':
    config = Config(sys.argv[1:])
    engine = Engine(config)
    server = Server("www", engine, config)
    server_thread = threading.Thread(target = engine.run)
    server_thread.daemon = True
    server_thread.start()
    server.run()