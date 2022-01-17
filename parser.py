import re
from lexer import Lexer
from data.classes import *

OrderOfOps = {
##        'number': 0,
##        'variable': 0,
##        'array' : 0,
        'lshift': 1,
        'rshift': 1,
        'mod': 1,
        'mask': 1,
        'insert': 1,
        '*': 2,
        '/': 2,
        '+': 3,
        '-': 3,
    }

class Parser:
    def __init__(self, reader):
        self.lexer = Lexer(reader)

    def parse(self):
        print('Parsing...')
        tree = []
        while self.lexer.next is not None:
            # ignore empty lines
            if self.lexer.next[0] == '\n':
                next(self.lexer)
            elif self.lexer.next[0] == '<':
                next(self.lexer) # discard '<'
                tag, value = self._parse_tag()
                if tag == 'region':
                    region = value.lower()
            else:
                expr = self._next_expression()
                tree.append(expr)
        print('Done.')
        return region, tree

    def _next_expression(self, expr=None):
        if self.lexer.next is None:
            return None
        if self.lexer.next[0] in '&()[]:,=\n':
            if expr is None:
                expr = next(self.lexer)
                if expr[0] == '(' and self.lexer.next[0] == 'type':
                    to = next(self.lexer)[1]
                    next(self.lexer) # discard ')'
                    var = next(self.lexer)[1]
                    return self._next_expression(Cast(var, to))
                elif expr[0] == '&':
                    type_, token = next(self.lexer)
                    if type_ == 'variable' and \
                       self.variables[token].type.endswith('[]'):
                        type_ = 'array'
                    return self._next_expression(Pointer(token, type_))
            return expr
        type_, token = next(self.lexer)
        if type_ in ['number', 'variable']:
            if type_ == 'variable':
                if self.lexer.next[0] == '[':
                    next(self.lexer) # discard '['
                    index = self._next_expression()
                    next(self.lexer) # discard ']'
                    type_ = self.variables[token].type[:-2]
                    node = Array(token, type_, index.value)
                else:
                    node = self.variables[token]
            elif type_ == 'number':
                node = Number(int(token, 0))
            if self.lexer.next[0] in ['comparator', 'connective'] \
               or self.lexer.next[1] == 'in':
                return node
            return self._next_expression(node)
        elif type_ == 'operator':
            expr1 = self._next_expression()
            return Operation(token, expr, expr1)
        elif type_ == 'comparator':
            expr1 = self._next_expression()
            return Conditional(token, expr, expr1)
        elif type_ == 'connective':
            expr1 = self._next_conditional()
            return CompoundConditional(token, expr, expr1)
        elif type_ == 'load/store':
            return self._parse_loadstore(token)
        elif type_ in ['type', 'function']:
            return (type_, token)
        elif type_ == 'reserved':
            if token == 'call':
                return self._parse_call()
            elif token == 'def':
                return self._parse_def()
            elif token == 'for':
                return self._parse_for()
            elif token == 'while':
                return self._parse_while()
            elif token == 'if':
                return self._parse_if()
            elif token == 'switch':
                return self._parse_switch()
            elif token in ['set', 'fset']:
                return self._parse_set(token)
            elif token == 'alloc':
                return self._parse_alloc()
            elif token == 'range':
                next(self.lexer) # discard '('
                expr = self._next_expression()
                next(self.lexer) # discard ')'
                return expr
            elif token == 'return':
                ret = self._next_expression()
                if not ret or type(ret) is not Variable:
                    return ('return', None)
                return ('return', ret)
            elif token in ['break', 'end', 'continue']:
                return (token,)

    def _parse_block(self, stop_at):
        next(self.lexer) # discard colon
        body = []
        while self.lexer.next[1] not in stop_at:
            # ignore empty lines
            if self.lexer.next[0] == '\n':
                next(self.lexer)
                continue
            body.append(self._next_expression())
        return tuple(body)

    def _parse_tag(self):
        type_ = next(self.lexer)[1]
        next(self.lexer) # discard '='
        value = next(self.lexer)[1]
        next(self.lexer) # discard '>'
        return (type_, value)

    def _parse_def(self):
        self.variables = {}
        _, name = next(self.lexer)
        next(self.lexer) # discard opening parenthesis
        params = []
        while self.lexer.next[0] != ')':
            expr = self._next_expression()
            var = self._next_variable(expr[1])
            params.append(var)
            if self.lexer.next[0] == ',':
                next(self.lexer)
        next(self.lexer) # discard closing parenthesis
        body = self._parse_block(['return'])
        return_val = self._next_expression()[1]
        return Function(name, tuple(params), body, return_val)

    def _parse_call(self):
        expr = self._next_expression()
        if type(expr) is Pointer:
            name = expr.target
            type_ = Pointer
        else:
            name = expr[1]
            type_ = Function
        next(self.lexer) # discard '('
        args = []
        while self.lexer.next[0] != ')':
            arg = self._next_expression()
            if self.lexer.next[0] == ',':
                next(self.lexer)
            args.append(arg)
        next(self.lexer) # discard ')'
        return Call(name, tuple(args), type_)

    def _parse_switch(self):
        var = self._next_expression()
        next(self.lexer) # discard ':'
        cases = set()
        blocks = []
        while self.lexer.next[1] != 'end':
            type_, token = next(self.lexer)
            if type_ == '\n':
                continue
            elif token == 'case':
                case = self._next_expression().value
                cases.add(case)
                body = self._parse_block(['case', 'break', 'switch'])
                if self.lexer.next[1] == 'break':
                    blocks.append(Case(tuple(cases), body))
                    next(self.lexer) # discard 'break'
                    cases = set()
            elif token == 'default':
                body = self._parse_block(['break'])
                if len(body) > 0:
                    blocks.append(Case((), body))
                next(self.lexer) # discard 'break'
        next(self.lexer) # discard 'end'
        return Switch(var, blocks)

    def _parse_if(self):
        def parse_next_block():
            condition = self._next_conditional()
            if self.lexer.next[0] == 'connective':
                condition = self._next_expression(condition)
            body = self._parse_block(['end', 'elif', 'else'])
            return (condition, body)

        blocks = []
        blocks.append(parse_next_block())
        while (token := next(self.lexer)[1]) == 'elif':
            blocks.append(parse_next_block())
        if token == 'else':
            blocks.append((None, self._parse_block(['end'])))
            next(self.lexer) # discard 'end'
        return If(blocks)

    def _parse_for(self):
        var = self._next_variable('int')
        next(self.lexer) # discard 'in'
        range_ = self._next_expression()
        body = self._parse_block(['end'])
        self._next_expression() # discard closing 'end'
        return For(var, range_, body)

    def _parse_while(self):
        condition = self._next_conditional()
        if self.lexer.next[0] == 'connective':
            condition = self._next_expression(condition)
        body = self._parse_block(['end'])
        self._next_expression() # discard closing 'end'
        return While(condition, body)

    def _parse_set(self, token):
        type_ = 'float' if token == 'fset' else 'int'
        var = self._next_variable(type_)
        next(self.lexer) # discard '='
        expr = self._next_expression()
        if type(expr) is Operation:
            expr = self._rotate_tree(expr)
            expr = self._order_operations(expr)
##            self._print_tree(expr)
        return Set(type_, var, expr)

##    def _print_tree(self, node, n=0):
##        tab = '   ' * n
##        if type(node) in [Array, Variable, Number, Cast]:
##            print(f'{tab}{node}')
##            return
##        print(f'{tab}{node.operator}')
##        print(f'{tab   }Left:')
##        self._print_tree(node.left, n+2)
##        print(f'{tab   }Right:')
##        self._print_tree(node.right, n+2)

    def _parse_alloc(self):
        name = next(self.lexer)[1]
        next(self.lexer) # discard '='
        type_ = self._next_expression()[1]
        next(self.lexer) # discard '['
        size = self._next_expression().value
        next(self.lexer) # discard ']'
        var = Variable(name, f'{type_}[]')
        self.variables[name] = var
        return Alloc(var, type_, size)

    def _parse_loadstore(self, op):
        if op[0] == 'l':
            var = self._next_variable('float' if op[1] == 'f' else 'int')
        else:
            var = self._next_expression()
        next(self.lexer) # discard ','
        offset = self._next_expression()
        next(self.lexer) # discard '('
        anchor = self._next_expression()
        next(self.lexer) # discard ')'
        return LoadStore(op, var, anchor, offset)

    def _next_conditional(self):
        expr = self._next_expression()
        condition = self._next_expression(expr)
        return condition

    def _next_variable(self, type_):
        name = self.lexer.next[1]
        if name not in self.variables:
            self.variables[name] = Variable(name, type_)
        var = self._next_expression()
        return var

    def _order_operations(self, node):
        if type(node) in [Number, Variable, Array, Cast]:
            return node
        branch = self._order_operations(node.left)
        if type(branch) is Operation \
           and OrderOfOps[branch.operator] > OrderOfOps[node.operator]:
            node = Operation(branch.operator,
                             branch.left,
                             Operation(node.operator,
                                       branch.right,
                                       node.right))
        else:
            node = Operation(node.operator, branch, node.right)
        return node

    # rotates a tree of math operations to be
    # left-skewed rather than right-skewed
    def _rotate_tree(self, tree):
        while type(tree.right) is Operation:
            tree = Operation(tree.right.operator,
                             Operation(tree.operator,
                                       tree.left,
                                       tree.right.left),
                             tree.right.right)
        return tree

##    def throw(self, msg):
##        raise Exception(f'{msg} (line {self.lexer.line})')
