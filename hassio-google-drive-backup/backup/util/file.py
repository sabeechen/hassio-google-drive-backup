class File():
    @classmethod
    def touch(cls, file):
        with open(file, "w"):
            pass
