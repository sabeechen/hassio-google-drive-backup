from bs4 import BeautifulSoup
import backup.exceptions
import inspect
import pytest
from backup.exceptions import GoogleCredGenerateError, KnownError, KnownTransient, SimulatedError, GoogleDrivePermissionDenied, InvalidConfigurationValue, LogicError, ProtocolError, NoBackup, NotUploadable, PleaseWait, UploadFailed
from .conftest import ReaderHelper


@pytest.mark.asyncio
async def test_verify_coverage(ui_server, reader: ReaderHelper):
    # Get the list of exception codes
    ignore = [
        KnownError,
        KnownTransient,
        SimulatedError,
        GoogleDrivePermissionDenied,
        InvalidConfigurationValue,
        LogicError,
        NoBackup,
        NotUploadable,
        PleaseWait,
        ProtocolError,
        UploadFailed,
        GoogleCredGenerateError,
    ]
    codes = {}
    for name, obj in inspect.getmembers(backup.exceptions):
        if inspect.isclass(obj) and (KnownError in obj.__bases__) and obj not in ignore:
            codes[obj().code()] = obj

    # Get the list of ui dialogs
    document = await reader.get("", json=False)
    page = BeautifulSoup(document, 'html.parser')

    dialogs = {}
    for div in page.find_all("div"):
        cls = div.get("class")
        if cls is None:
            continue
        if "error_card" in cls:
            for specific_class in cls:
                if specific_class in dialogs:
                    dialogs[specific_class] = dialogs[specific_class] + 1
                else:
                    dialogs[specific_class] = 1

    # Make sure exactly one dialog has the class
    for code in codes.keys():
        assert dialogs[code] == 1
