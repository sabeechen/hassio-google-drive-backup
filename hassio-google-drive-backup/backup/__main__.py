import requests
import sys
import json

from .config import Config
from .harequests import HaRequests
from .hasource import HaSource
from .drivesource import DriveSource
from .driverequests import DriveRequests
from .globalinfo import GlobalInfo
from .uiserver import UIServer
from .settings import _LOOKUP
from .coordinator import Coordinator
from .time import Time
from .model import Model
from .helpers import formatException
from .logbase import LogBase
from .syncer import Scyncer
from .haupdater import HaUpdater
from .watcher import Watcher
from .debugworker import DebugWorker
from .resolver import Resolver
from .exceptions import KnownError
from .estimator import Estimator


def getConfig(resolver):
    if len(sys.argv) > 1:
        with open("backup/dev/data/{0}_options.json".format(sys.argv[1])) as f:
            overrides = json.load(f)
        config = Config(resolver)
        for override in overrides:
            config.override(_LOOKUP[override], overrides[override])
        return config
    else:
        return Config(resolver)


def main():
    # bootstrap
    time = Time()
    resolver = Resolver(time)
    with resolver:
        config = getConfig(resolver)
        info = GlobalInfo(time)
        ha_requests = HaRequests(config, requests)
        ha_source = HaSource(config, time, ha_requests, info)
        ha_updater = HaUpdater(ha_requests, config, time, info)
        ha_updater.start()

        debug_worker = DebugWorker(time, info, config)
        debug_worker.start()

        # Connect to supevisor, load config
        while(True):
            try:
                ha_source.init()
                break
            except Exception as e:
                if isinstance(e, KnownError):
                    LogBase().critical("Unable to reach Hassio supervisor.")
                    LogBase().critical(e.message())
                else:
                    LogBase().critical("Unable to reach Hassio supervisor.")
                    LogBase().critical(formatException(e))
                time.sleep(10)

        drive_requests = DriveRequests(config, time, requests, resolver)
        drive_source = DriveSource(config, time, drive_requests, info)
        estimator = Estimator(config, info)
        model = Model(config, time, ha_source, drive_source, info, estimator)
        coord = Coordinator(model, time, config, info, ha_updater, estimator)

        # Start the UI server
        # SOMEDAY: Someday: Server shoudl start before ha_source.init() and display an error page if we can't connect to the coordinator
        server = UIServer(coord, ha_source, ha_requests, time, config, info, estimator)
        server.run()

        watcher: Watcher = Watcher(time, config)

        # Startup syncer, and then wait
        syncer = Scyncer(time, coord, [coord, ha_source, drive_source, watcher, server])
        syncer.start()
        syncer.join()


if __name__ == '__main__':
    main()
