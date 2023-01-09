import asyncio
from aiohttp import web
from aiohttp.web import Request
from injector import inject, singleton
from backup.time import Time
from backup.model import Model, Coordinator
from backup.logger import getLogger
from datetime import timedelta

logger = getLogger(__name__)


@singleton
class Debug():
    @inject
    def __init__(self, model: Model, coord: Coordinator, time: Time):
        self._model = model
        self._coord = coord
        self._time = time

    async def getTasks(self, request):
        resp = []
        for task in asyncio.all_tasks():
            data = {
                "name": task.get_name(),
                "state": str(task._state),
                "coroutine": str(task.get_coro())
            }

            # Get exception
            try:
                ex = task.exception()
                if ex is None:
                    data['exception'] = "None"
                else:
                    data['exception'] = logger.formatException(ex)
            except asyncio.CancelledError:
                data['exception'] = "CancelledError"
            except asyncio.InvalidStateError:
                data['exception'] = "Unfinished"
            except Exception:
                pass

            # Get result
            try:
                ret = task.result()
                if ex is None:
                    data['result'] = "None"
                else:
                    data['result'] = str(ret)
            except asyncio.CancelledError:
                data['result'] = "CancelledError"
            except asyncio.InvalidStateError:
                data['result'] = "Unfinished"
            except Exception:
                pass
            data['stack'] = []
            for frame in task.get_stack():
                data['stack'].append(str(frame))
            resp.append(data)
        return web.json_response(resp)

    async def simerror(self, request: Request):
        error = request.query.get("error", "")
        if len(error) == 0:
            self._model.simulate_error = None
        else:
            self._model.simulate_error = error
        self._coord.trigger()
        return web.json_response({})

    async def timeoffset(self, request: Request):
        delta = int(request.query.get("offset", ""))
        self._time.offset = timedelta(seconds=delta)
        return web.json_response({})
