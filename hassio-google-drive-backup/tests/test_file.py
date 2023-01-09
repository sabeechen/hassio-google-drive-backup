

from backup.file import File
from os.path import exists, join
from os import remove
import pytest
import json

TEST_DATA = "when you press my special key I play a little melody"


def readfile(path):
    with open(path) as f:
        return f.read()


@pytest.mark.asyncio
async def test_basic(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    backup_path = join(tmpdir, "test.json.backup")

    assert not File.exists(path)
    File.write(path, TEST_DATA)
    assert File.exists(path)
    assert readfile(path) == TEST_DATA
    assert readfile(backup_path) == TEST_DATA
    assert File.read(path) == TEST_DATA

    File.delete(path)
    assert not exists(path)
    assert not exists(backup_path)
    assert not File.exists(path)


@pytest.mark.asyncio
async def test_file_deleted(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    File.write(path, TEST_DATA)
    remove(path)
    assert File.read(path) == TEST_DATA


@pytest.mark.asyncio
async def test_backup_deleted(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    backup_path = join(tmpdir, "test.json.backup")
    File.write(path, TEST_DATA)
    remove(backup_path)
    assert File.read(path) == TEST_DATA

@pytest.mark.asyncio
async def test_decode_error(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    File.write(path, TEST_DATA)
    with open(path, "w"):
        # emptys the file contents
        pass
    with open(path) as f:
        assert len(f.read()) == 0
    assert File.read(path) == TEST_DATA
