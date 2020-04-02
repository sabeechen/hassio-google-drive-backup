from bs4 import BeautifulSoup
from os.path import join, abspath
import backup.exceptions
import inspect
from backup.exceptions import KnownError, KnownTransient, SimulatedError, GoogleDrivePermissionDenied, InvalidConfigurationValue, LogicError, ProtocolError, NoSnapshot, NotUploadable, PleaseWait, UploadFailed


def test_verify_coverage():
    # Get the list of exception codes
    ignore = [
        KnownError,
        KnownTransient,
        SimulatedError,
        GoogleDrivePermissionDenied,
        InvalidConfigurationValue,
        LogicError,
        NoSnapshot,
        NotUploadable,
        PleaseWait,
        ProtocolError,
        UploadFailed
    ]
    codes = {}
    for name, obj in inspect.getmembers(backup.exceptions):
        if inspect.isclass(obj) and (KnownError in obj.__bases__) and obj not in ignore:
            codes[obj().code()] = obj

    # Get the list of ui dialogs
    dialogs = {}
    with open(abspath(join(__file__, "..", "..", "backup", "static", "working.html")), "r") as f:
        text = f.read()
    page = BeautifulSoup(text, 'html.parser')
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
