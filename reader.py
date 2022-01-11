class Reader:
    def __init__(self, path):
        self.path = path
        self.iter = self._next_char()

    def _next_char(self):
        c = self.file.read(1)
        while c != '':
            yield c
            c = self.file.read(1)
        while True:
            yield None

    def __next__(self):
        return next(self.iter)

    def __enter__(self):
        self.file = open(self.path)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.file.close()
