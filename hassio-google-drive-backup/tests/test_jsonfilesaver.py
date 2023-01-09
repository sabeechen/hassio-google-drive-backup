

from backup.file import JsonFileSaver
from os.path import exists, join
from os import remove
import pytest
import json

TEST_DATA = {
    'info': "and the value",
    'some': 3
}


def readfile(path):
    with open(path) as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_basic(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    backup_path = join(tmpdir, "test.json.backup")

    assert not JsonFileSaver.exists(path)
    JsonFileSaver.write(path, TEST_DATA)
    assert JsonFileSaver.exists(path)
    assert readfile(path) == TEST_DATA
    assert readfile(backup_path) == TEST_DATA
    assert JsonFileSaver.read(path) == TEST_DATA

    JsonFileSaver.delete(path)
    assert not exists(path)
    assert not exists(backup_path)
    assert not JsonFileSaver.exists(path)


@pytest.mark.asyncio
async def test_file_deleted(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    JsonFileSaver.write(path, TEST_DATA)
    remove(path)
    assert JsonFileSaver.read(path) == TEST_DATA


@pytest.mark.asyncio
async def test_backup_deleted(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    backup_path = join(tmpdir, "test.json.backup")
    JsonFileSaver.write(path, TEST_DATA)
    remove(backup_path)
    assert JsonFileSaver.read(path) == TEST_DATA

@pytest.mark.asyncio
async def test_decode_error(tmpdir: str) -> None:
    path = join(tmpdir, "test.json")
    JsonFileSaver.write(path, TEST_DATA)
    with open(path, "w"):
        # emptys the file contents
        pass
    with open(path) as f:
        assert len(f.read()) == 0
    assert JsonFileSaver.read(path) == TEST_DATA
