import re

class Lexer:
    def __init__(self, reader):
        self.reader = reader
        self.line = 1
        self.iter = self.lex()
        self.tokens = self._next_token()
        self.next = next(self.iter)

    def lex(self):
        token = next(self.tokens)
        while token is not None:
            if token == '//':
                self._scan_comment()
                yield ('\n', None)
            elif token == '"':
                string = self._scan_string()
                yield ('string', string)
            elif self._is_special(token):
                yield (token, None)
            elif self._is_number(token):
                yield ('number', token)
            elif self._is_operation(token):
                yield ('operator', token)
            elif self._is_connective(token):
                yield ('connective', token)
            elif self._is_type(token):
                yield ('type', token)
            elif self._is_reserved(token):
                yield ('reserved', token)
            elif self._is_loadstore(token):
                yield ('load/store', token)
            elif self._is_comparator(token):
                yield ('comparator', token)
            elif self._is_variable(token):
                yield ('variable', token)
            elif self._is_function(token):
                yield ('function', token)
            else:
                self.throw(f"Invalid token '{token}'")
            token = next(self.tokens)
        while True:
            yield None

    def _scan_comment(self):
        token = ''
        while token != '\n':
            token = next(self.tokens)

    def _scan_string(self):
        s = ''
        while (token := next(self.tokens)) not in '"\n':
            s += token
        if token != '"':
            self.throw(f"Unclosed string")
        return s

    def _is_special(self, token):
        return token in '()[]<>"&:,=\n'

    def _is_operation(self, token):
        return token in '+-*/' \
               or token in ['mask', 'insert', 'mod', 'lshift', 'rshift']

    def _is_connective(self, token):
        return token in ['and', 'or']

    def _is_number(self, token):
        try:
            val = int(token, 0)
            if val > 0xffffffff:
                self.throw(f"Int literal '{val}' exceeds 32-bit maximum")
            return True
        except:
            return False

    def _is_type(self, token):
        return token in ['int', 'float']

    def _is_reserved(self, token):
        return token in ['alloc', 'and', 'break', 'call', 'case', 'continue',
                         'def', 'elif', 'else', 'end', 'for', 'fset', 'if',
                         'in', 'or', 'range', 'return', 'set', 'switch', 'while']

    def _is_loadstore(self, token):
        return token in ['lbz', 'lbzu', 'lfd', 'lfdu', 'lfs', 'lfsu',
                         'lha', 'lhau', 'lhz', 'lhzu', 'lwz', 'lwzu',
                         'stb', 'stbu', 'stfd', 'stfdu', 'stfs', 'stfsu',
                         'sth', 'sthu', 'stw', 'stwu']

    def _is_comparator(self, token):
        return token in ['eq', 'ge', 'gt', 'le', 'lt', 'ne']

    def _is_variable(self, token):
        return bool(re.match('[a-z]', token) and re.fullmatch('[_0-9a-zA-Z]+', token))

    def _is_function(self, token):
        return bool(re.match('[A-Z]', token) and re.fullmatch('[_0-9a-zA-Z]+', token))
    
    def _next_token(self):
        token = ''
        c = next(self.reader)
        while c is not None:
            if c in '()[]<>"&:,= \t\r\n':
                if len(token) > 0:
                    yield token
                    token = ''
                if self._is_special(c):
                    yield c
            else:
                token += c
            c = next(self.reader)
        if len(token) > 0:
            yield token
        while True:
            yield None

    def __next__(self):
        val = self.next
        if val and val[0] == '\n':
            self.line += 1
        self.next = next(self.iter)
        return val

    def throw(self, msg):
        raise Exception(f'{msg} (line {self.line})')
