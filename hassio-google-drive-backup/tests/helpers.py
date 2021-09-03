import json
import tarfile
import pytest
import platform
import os
from datetime import datetime
from io import BytesIO, IOBase

from aiohttp import ClientSession
from injector import inject, singleton

from backup.util import AsyncHttpGetter
from backup.model import SimulatedSource
from backup.time import Time
from backup.config import CreateOptions

all_folders = [
    "share",
    "ssl",
    "addons/local",
    "homeassistant"
]
all_addons = [
    {
        "name": "Sexy Robots",
        "slug": "sexy_robots",
        "description": "The robots you already know, but sexier. See what they don't want you to see.",
        "version": "0.69",
        "size": 1,
        "logo": True,
        "state": "started"
    },
    {
        "name": "Particle Accelerator",
        "slug": "particla_accel",
        "description": "What CAN'T you do with Home Assistant?",
        "version": "0.5",
        "size": 500.3,
        "logo": True,
        "state": "started"
    },
    {
        "name": "Empty Addon",
        "slug": "addon_empty",
        "description": "Explore the meaning of the universe by contemplating whats missing.",
        "version": "0.-1",
        "size": 1024 * 1024 * 1024 * 21.2,
        "logo": False,
        "state": "started"
    }
]


def skipForWindows():
    if platform.system() == "Windows":
        pytest.skip("This test can't be run in windows environments")


def skipForRoot():
    if os.getuid() == 0:
        pytest.skip("This test can't be run as root")


def createBackupTar(slug: str, name: str, date: datetime, padSize: int, included_folders=None, included_addons=None, password=None) -> BytesIO:
    backup_type = "full"
    if included_folders is not None:
        folders = included_folders.copy()
    else:
        folders = all_folders.copy()

    if included_addons is not None:
        backup_type = "partial"
        addons = []
        for addon in all_addons:
            if addon['slug'] in included_addons:
                addons.append(addon)
    else:
        addons = all_addons.copy()

    backup_info = {
        "slug": slug,
        "name": name,
        "date": date.isoformat(),
        "type": backup_type,
        "protected": password is not None,
        "homeassistant": "0.92.2",
        "folders": folders,
        "addons": addons,
        "repositories": [
            "https://github.com/hassio-addons/repository"
        ]
    }
    stream = BytesIO()
    tar = tarfile.open(fileobj=stream, mode="w")
    add(tar, "backup.json", BytesIO(json.dumps(backup_info).encode()))
    add(tar, "padding.dat", getTestStream(padSize))
    tar.close()
    stream.seek(0)
    stream.size = lambda: len(stream.getbuffer())
    return stream


def add(tar, name, stream):
    info = tarfile.TarInfo(name)
    info.size = len(stream.getbuffer())
    stream.seek(0)
    tar.addfile(info, stream)


def parseBackupInfo(stream: BytesIO):
    with tarfile.open(fileobj=stream, mode="r") as tar:
        info = tar.getmember("backup.json")
        with tar.extractfile(info) as f:
            backup_data = json.load(f)
            backup_data['size'] = float(
                round(len(stream.getbuffer()) / 1024.0 / 1024.0, 2))
            backup_data['version'] = 'dev'
            return backup_data


def getTestStream(size: int):
    """
    Produces a stream of repeating prime sequences to avoid accidental repetition
    """
    arr = bytearray()
    while True:
        for prime in [4759, 4783, 4787, 4789, 4793, 4799, 4801, 4813, 4817, 4831, 4861, 4871, 4877, 4889, 4903, 4909, 4919, 4931, 4933, 4937]:
            for x in range(prime):
                if len(arr) < size:
                    arr.append(x % 255)
                else:
                    break
            if len(arr) >= size:
                break
        if len(arr) >= size:
            break
    return BytesIO(arr)


async def compareStreams(left, right):
    await left.setup()
    await right.setup()
    while True:
        from_left = await left.read(1024 * 1024)
        from_right = await right.read(1024 * 1024)
        if len(from_left.getbuffer()) == 0:
            assert len(from_right.getbuffer()) == 0
            break
        if from_left.getbuffer() != from_right.getbuffer():
            print("break!")
        assert from_left.getbuffer() == from_right.getbuffer()


class IntentionalFailure(Exception):
    pass


class HelperTestSource(SimulatedSource):
    def __init__(self, name):
        super().__init__(name)
        self.allow_create = True
        self.allow_save = True

    def reset(self):
        self.saved = []
        self.deleted = []
        self.created = []

    def assertThat(self, created=0, deleted=0, saved=0, current=0):
        assert len(self.saved) == saved
        assert len(self.deleted) == deleted
        assert len(self.created) == created
        assert len(self.current) == current
        return self

    def assertUnchanged(self):
        self.assertThat(current=len(self.current))
        return self

    async def create(self, options: CreateOptions):
        if not self.allow_create:
            raise IntentionalFailure()
        return await super().create(options)

    async def save(self, backup, bytes: IOBase = None):
        if not self.allow_save:
            raise IntentionalFailure()
        return await super().save(backup, bytes=bytes)


@singleton
class Uploader():
    @inject
    def __init__(self, host, session: ClientSession, time: Time):
        self.host = host
        self.session = session
        self.time = time

    async def upload(self, data):
        async with await self.session.post(self.host + "/uploadfile", data=data) as resp:
            resp.raise_for_status()
        source = AsyncHttpGetter(self.host + "/readfile", {}, self.session, time=self.time)
        return source
