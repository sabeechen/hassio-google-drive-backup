class Wrapper(object):
    def __init__(self, obj):
        self._wrapped_obj = obj
    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self._wrapped_obj, attr)
    
    def release(self):
        return self._wrapped_obj.release()