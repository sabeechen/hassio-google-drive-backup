import cgi


class Context(object):
    def __init__(self):
        pass

    def getAuthUrl(self):
        pass

    def generateCredentials(self):
        pass

    def header(self, key):
        return cgi.FieldStorage().getvalue(key)


class Response(object):
    def __init__(self, http_code, headers, content):
        self.http_code = http_code
        self.headers = headers
        self.content = content

    def render(self):
        print("Status: {0}".format(self.http_code))
        for header in self.headers:
            print("{0}: {1}".format(header, self.headers[header]))
        print("")
        print(self.content)
