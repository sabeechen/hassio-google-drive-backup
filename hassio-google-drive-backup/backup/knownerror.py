class KnownError(Exception):
    def __init__(self, message: str, detail: str=""):
        self.detail = detail
        self.message = message
