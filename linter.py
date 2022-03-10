import os, re, sys
from lexer import Lexer
from reader import Reader
from data.classes import *
import data.pbr_globals as globals_
import data.ops as ops

def is_operand(type):
    return type in ['number', 'variable', 'array[]', 'cast', 'operation']

def path_in_set(paths, path):
    return any(os.path.samefile(f, path) for f in paths)

class Linter:
    def __init__(self, reader):
        self.path = reader.path
        self.lexer = Lexer(reader)
        self.region = None

    def _get_operand_type(self, expr):
        if expr[0] == 'number':
            # float literals are not currently supported
            type_ = 'int'
        elif expr[0] in 'variable':
            type_ = self.variables[expr[1]]
        elif expr[0] == 'array[]':
            type_ = self.variables[expr[1]]
            type_ = type_[:type_.index('[')] # remove '[]'
        elif expr[0] == 'cast':
            type_ = expr[1]
        elif expr[0] == 'operation':
            type_ = expr[4]
        return type_

    def lint(self, linted=None):
        # tags
        while self.lexer.next is not None \
              and self.lexer.next[1] not in ['import', 'def']:
            type_, token = next(self.lexer)
            if type_ == '<':
                tag, value = self._lint_tag()
                if tag == 'region':
                    if self.region is not None:
                        self.throw(f"A script file cannot have multiple region tags")
                    self.region = value
            elif type_ != '\n':
                self.throw(f"Statements cannot appear outside of function bodies")
        if self.region is None:
            self.throw(f"Missing region tag")
        # imports
        imports = set()
        while self.lexer.next is not None \
              and self.lexer.next[1] != 'def':
            type_, token = next(self.lexer)
            if token == 'import':
                path = self._lint_import()
                if path_in_set(imports, path):
                    self.throw(f"Duplicate import")
                imports.add(path)
            elif type_ == '<':
                self.throw(f"Tags must appear at the start of the file")
            elif type_ != '\n':
                self.throw(f"Statements cannot appear outside of function bodies")
        # functions
        self.functions = set()
        self.function_uses = {}
        while self.lexer.next is not None:
            type_, token = next(self.lexer)
            if token == 'def':
                self._lint_def()
            elif type_ == '<':
                self.throw(f"Tags must appear at the start of the file")
            elif type_ != '\n':
                self.throw(f"Statements cannot appear outside of function bodies")

        # lint imported scripts recursively
        if linted is None:
            linted = set()
        if not path_in_set(linted, self.path):
            linted.add(self.path)
            for path in imports:
                with Reader(path) as reader:
                    linter = Linter(reader)
                    linter.lint(linted)
                    self.functions |= linter.functions
            # only validate function uses the first time a script is
            # visited since future visits won't visit imports
            for func in sorted(self.function_uses,
                               key=lambda x: self.function_uses[x]):
                if not func.startswith('FUN_') \
                   and func not in self.functions \
                   and func not in globals_.functions[self.region]:
                    self.throw(f"Function '{func}' is not defined",
                               line=self.function_uses[func])
        self.files = linted

    def _next_expression(self, expr=None, stop=False):
        if self.lexer.next[0] in ',):=\n':
            if expr is None:
                return next(self.lexer)
            return expr
        elif self.lexer.next[0] == '&':
            next(self.lexer) # discard '&'
            expr = self._next_expression(stop=True)
            if expr[0] not in ['function', 'array', 'variable']:
                self.throw(f"Cannot point to type '{expr[0]}'")
            node = ('pointer', expr[0], expr[1])
            if stop:
                return node
            return self._next_expression(node)
        elif self.lexer.next[0] == '(':
            if expr is not None:
                return expr
            expr = next(self.lexer)
            if self.lexer.next[0] == 'type':
                to = next(self.lexer)[1]
                if next(self.lexer)[0] != ')':
                    self.throw(f"Invalid cast operation")
                expr = self._next_expression(stop=True)
                if expr[0] != 'variable':
                    self.throw(f"Cannot cast type '{expr[0]}'")
                if stop:
                    return ('cast', to)
                return self._next_expression(('cast', to))
            return expr
        elif self.lexer.next[0] == '[':
            next(self.lexer) # discard '['
            if expr is None or expr[0] != 'array':
                self.throw(f"Invalid use of '['")
            type_, index = next(self.lexer)
            if type_ != 'number':
                self.throw(f"Array indices cannot be of type '{type_}'")
            match = re.search(r'\[([0-9]+)\]', self.variables[expr[1]])
            size = int(match.group(1), 0)
            index = int(index, 0)
            if index >= size:
                self.throw(f"Array index out of bounds for array of size {size}")
            if next(self.lexer)[0] != ']':
                self.throw(f"Invalid array; missing ']'")
            return self._next_expression(('array[]', expr[1]))

        type_, token = next(self.lexer)
        if type_ in ['number', 'variable']:
            if type_ == 'variable':
                if token not in self.variables:
                    self.throw(f"Use of uninitialized variable '{token}'")
                elif '[' in self.variables[token]:
                    type_ = 'array'
            if stop or self.lexer.next[0] == 'connective':
                return (type_, token)
            return self._next_expression((type_, token))
        elif type_ == 'function':
            if token.startswith('FUN_'):
                try:
                    addr = int(token[4:], 16)
                    if addr < 0x80000000 or addr > 0x8fffffff:
                        self.throw(f"Global function reference out of bounds")
                except ValueError:
                    self.throw(f"Invalid global function reference '{token}'")
            self.function_uses[token] = self.lexer.line
            return (type_, token)
        elif type_ == 'operator':
            left = expr
            if left is None:
                self.throw(f"Invalid '{token}' operation")
            elif not is_operand(left[0]):
                self.throw(f"Cannot operate on type '{left[0]}'")
            right = self._next_expression(stop=True)
            if not is_operand(right[0]):
                self.throw(f"Cannot operate on type '{right[0]}'")
            if left[0] == right[0] == 'number':
                self.throw(f"Operations between two literals are not supported")
            type_ = self._get_operand_type(left)
            if type_ != self._get_operand_type(right):
                self.throw(f"Type mismatch in operation")
            node = ('operation', token, left, right, type_)
            if stop:
                return node
            return self._next_expression(node)
        elif type_ == 'comparator':
            left = expr
            if left is None:
                self.throw(f"Invalid '{token}' comparison")
            elif left[0] not in ['variable', 'operation']:
                self.throw(f"Type '{left[0]}' cannot appear on the left of a comparison")
            # I don't think there's actually any issue here,
            # so I may end up allowing it
            if left[0] == 'operation' and 'operation' in [expr[2][0], expr[3][0]]:
                self.throw(f"Cannot in-line more than one operation in a comparison")
            right = self._next_expression()
            if right[0] not in ['number', 'variable']:
                self.throw(f"Type '{right[0]}' cannot appear on the right of a comparison")
            if self._get_operand_type(left) != self._get_operand_type(right):
                self.throw(f"Type mismatch in comparison")
            node = ('comparison', token, left, right)
            if stop:
                return node
            return self._next_expression(node)
        elif type_ == 'connective':
            left = expr
            if left is None:
                self.throw(f"Invalid '{token}' conditional")
            elif left[0] != 'comparison':
                self.throw(f"Cannot apply '{token}' to type '{left[0]}'")
            right = self._next_expression()
            if right[0] != 'comparison':
                self.throw(f"Cannot apply '{token}' to type '{right[0]}'")
            return ('conjunction', token, left, right)
        elif type_ == 'reserved':
            if token == 'range':
                if next(self.lexer)[0] != '(':
                    self.throw(f"Invalid 'range' statement; missing '('")
                arg = self._next_expression()
                if arg[0] not in ['number', 'variable']:
                    self.throw(f"Cannot use type '{arg[0]}' as the argument for 'range'")
                elif arg[0] == 'number' and int(arg[1], 0) < 0:
                    self.throw(f"Argument to 'range' cannot be negative")
                elif arg[0] == 'variable' and self.variables[arg[1]] != 'int':
                    type_ = self.variables[arg[1]]
                    self.throw(f"Cannot use '{type_}' variable as argument for 'range'")
                if next(self.lexer)[0] != ')':
                    self.throw(f"Invalid 'range' statement; missing ')'")
                return ('range', arg)
            elif token == 'call':
                func = self.lexer.next
                self._lint_call()
                return ('call', func)
        return (type_, token)

    def _lint_tag(self):
        type_, tag = next(self.lexer)
        if type_ != 'variable' or tag != 'region':
            self.throw(f"Invalid tag type '{tag}'")
        if next(self.lexer)[0] != '=':
            self.throw(f"Invalid tag; missing '='")
        type_, value = next(self.lexer)
        if type_ != 'string':
            self.throw(f"Invalid tag value of type '{type_}'")
        elif tag == 'region' \
             and value.lower() not in ['ntsc-j', 'ntsc-u', 'pal']:
            self.throw(f"Invalid region '{value}'")
        if next(self.lexer)[0] != '>':
            self.throw(f"Unclosed tag")
        if next(self.lexer)[0] != '\n':
            self.throw(f"Tags must be on their own line")
        return (tag, value.lower())

    def _lint_import(self):
        type_, path = next(self.lexer)
        if type_ != 'string':
            self.throw(f"Invalid import statement")
        if not os.path.exists(path):
            self.throw(f"No such file: '{path}'")
        elif os.path.samefile(self.path, path):
            self.throw(f"Attempted self-import")
        if next(self.lexer)[0] != '\n':
            self.throw(f"Invalid import statement")
        return path

    def _lint_def(self):
        self.variables = {}
        self.in_loop = False
        self.in_switch = False

        type_, name = next(self.lexer)
        if type_ != 'function':
            msg = f"Invalid function name '{name}'"
            if type_ == 'variable':
                msg += " - function names must start with a capital letter"
            self.throw(msg)
        elif name.startswith('FUN_'):
            self.throw(f"Invalid function name '{name}'; the prefix 'FUN_' is reserved for global function references")
        elif name in self.functions:
            self.throw(f"Duplicate function name '{name}'")
        elif name in globals_.functions:
            print(f"WARNING: function '{name}' will hide the global function of the same name")
        self.functions.add(name)
        if next(self.lexer)[0] != '(':
            self.throw("Invalid function definition; missing '('")

        while self.lexer.next[0] != ')':
            type_, type = next(self.lexer)
            if type not in ['int', 'float']:
                self.throw("Invalid function definition")
            type_, var = next(self.lexer)
            if type_ != 'variable':
                self.throw("Invalid function definition")
            self.variables[var] = type
            if self.lexer.next[0] not in ',)':
                self.throw("Invalid function definition")
            if self.lexer.next[0] == ',':
                next(self.lexer)
        next(self.lexer) # discard ')'
        self._lint_block('return')
        if self.lexer.next:
            expr = self._next_expression()
            if expr[0] not in ['\n', 'variable']:
                self.throw(f"Invalid return value of type '{expr[0]}")

    def _lint_switch(self):
        expr = self._next_expression()
        if expr[0] != 'variable':
            self.throw(f"Cannot switch on type '{expr[0]}'")
        # switches aren't true blocks, so can't use self._lint_block()
        if next(self.lexer)[0] != ':':
            self.throw("Invalid 'case' statement; missing ':'")
        if next(self.lexer)[0] != '\n':
            self.throw("Invalid 'case' statement")
        self.in_switch = True
        num_cases = 0
        default = False
        while self.lexer.next and self.lexer.next[1] != 'end':
            type_, token = next(self.lexer)
            if type_ == '\n':
                continue
            elif token == 'case':
                if default:
                    self.throw(f"Additional cases cannot appear after a 'default' block")
                # handle fall-through
                while token == 'case':
                    num_cases += 1
                    type_, token = next(self.lexer)
                    if type_ != 'number':
                        self.throw(f"Invalid 'case' statement; missing case value")
                    elif int(token, 0) < 0:
                        self.throw("Case values cannot be negative")
                    lines = self._lint_block(['case', 'break'])
                    if lines[-1] == 'case' and len(lines) > 1:
                        self.throw(f"Invalid case block; missing 'break' statement")
                    token = lines[-1]
            elif token == 'default':
                if default:
                    self.throw(f"Switches cannot contain multiple 'default' blocks")
                self._lint_block('break')
                # we don't just break because we need to
                # consume any remaining newlines
                default = True
            else:
                self.throw(f"Statements cannot appear outside of 'case'/'default' blocks in switches")
        if self.lexer.next is None:
            self.throw(f"Unclosed block")
        if num_cases == 0:
            self.throw(f"Cannot have a switch statement without any 'case' blocks")
        next(self.lexer) # discard 'end'
        self.in_switch = False

    def _lint_if(self):
        expr = self._next_expression()
        if expr[0] not in ['comparison', 'conjunction']:
            self.throw(f"Invalid 'if' statement")
        token = self._lint_block(['elif', 'else', 'end'])[-1]
        while token == 'elif':
            expr = self._next_expression()
            if expr[0] not in ['comparison', 'conjunction']:
                self.throw(f"Invalid 'elif' statement")
            token = self._lint_block(['elif', 'else', 'end'])[-1]
        if token == 'else':
            self._lint_block('end')

    def _lint_for(self):
        type_, var = next(self.lexer)
        if type_ != 'variable':
            self.throw(f"Invalid 'for' statement")
        self.variables[var] = 'int'
        if next(self.lexer)[1] != 'in':
            self.throw(f"Invalid 'for' statement; missing 'in'")
        expr = self._next_expression()
        if expr[0] != 'range':
            self.throw(f"Invalid 'for' statement; expected 'range', not '{expr[0]}'")
        if expr[1][0] == 'variable' and expr[1][1] == var:
            self.throw(f"Cannot use '{var}' as both iterator and range argument")
        self.in_loop = True
        self._lint_block('end')
        self.in_loop = False

    def _lint_while(self):
        expr = self._next_expression()
        if expr[0] not in ['comparison', 'conjunction']:
            self.throw(f"Invalid 'while' statement")
        self.in_loop = True
        self._lint_block('end')
        self.in_loop = False

    def _lint_alloc(self):
        type_, var = next(self.lexer)
        if type_ != 'variable':
            self.throw(f"Invalid 'alloc' statement")
        elif var in self.variables:
            self.throw(f"Duplicate array name '{var}'")
        if next(self.lexer)[0] != '=':
            self.throw(f"Invalid 'alloc' statement; missing '='")
        type_, type = next(self.lexer)
        if type_ != 'type':
            self.throw(f"Invalid 'alloc' statement")
        if next(self.lexer)[0] != '[':
            self.throw(f"Invalid 'alloc' statement; missing '['")
        type_, size = next(self.lexer)
        if type_ != 'number':
            self.throw(f"Invalid 'alloc' statement")
        size = int(size, 0)
        if size <= 0:
            value = 'zero' if size == 0 else 'negative'
            self.throw(f"Array size cannot be {value}")
        if next(self.lexer)[0] != ']':
            self.throw(f"Invalid 'alloc' statement; missing ']'")
        self.variables[var] = f'{type}[{size}]'

    def _lint_call(self):
        expr = self._next_expression()
        if expr[0] not in ['function', 'pointer']:
            self.throw(f"Invalid call statement")
        elif expr[0] == 'pointer' and expr[1] != 'variable':
            self.throw(f"Invalid pointer for function call")
        if next(self.lexer)[0] != '(':
            self.throw(f"Invalid function call; missing '('")
        count = 0
        while self.lexer.next[0] != ')':
            expr = self._next_expression()
            if expr[0] not in ['number', 'pointer', 'variable']:
                msg = f"Invalid function argument of type '{expr[0]}'"
                if expr[0] == 'array':
                    msg += f" (did you mean '&{expr[1]}'?)"
                self.throw(msg)
            elif expr[0] == 'pointer' and expr[1] == 'variable':
                self.throw(f"Cannot use '{expr[1]}' pointer as function argument")
            if self.lexer.next[0] not in ',)':
                self.throw(f"Invalid function call")
            if self.lexer.next[0] == ',':
                next(self.lexer)
            count += 1
        next(self.lexer) # discard ')'
        if count > 8:
            self.throw(f"Cannot pass more than 8 parameters in a function call")

    def _lint_set(self, op):
        type_, var = next(self.lexer)
        if type_ != 'variable':
            self.throw(f"Invalid '{op}' statement; cannot assign to type '{type_}'")
        # handle array assignment
        if self.lexer.next[0] == '[':
            if var not in self.variables:
                self.throw(f"Use of uninitialized variable '{var}'")
            expr = self._next_expression(('array', var))
        if next(self.lexer)[0] != '=':
            self.throw(f"Invalid '{op}' statement; missing '='")
        expr = self._next_expression()
        if not is_operand(expr[0]) and expr[0] != 'call' \
           and (op != 'set' or expr[0] != 'pointer'):
            self.throw(f"Invalid '{op}' statement; cannot assign type '{expr[0]}'")
        if op == 'fset':
            self._lint_fset_r(expr)
        else:
            self._lint_set_r(expr)
        type = 'float' if op == 'fset' else 'int'
        if is_operand(expr[0]) and self._get_operand_type(expr) != type:
            self.throw(f"Invalid '{op}' statement; value not of type '{type}'")
        if var not in self.variables:
            self.variables[var] = type

    def _lint_set_r(self, expr):
        if expr[0] == 'cast' and expr[1] != 'int':
            self.throw(f"Cannot cast to type '{expr[1]}' in 'set' statement")
        elif expr[0] == 'pointer' and expr[1] != 'function':
            self.throw(f"Cannot assign '{expr[1]}' pointer to variable")
        elif expr[0] == 'operation':
            if expr[1] == 'insert':
                if expr[2][0] != 'operation' or expr[2][1] != 'mask':
                    self.throw(f"Cannot use 'insert' except after a 'mask' operation")
                elif expr[2][3][0] != 'number':
                    self.throw(f"Insert mask must be of type 'number', not '{expr[2][0]}'")
            self._lint_set_r(expr[2])
            self._lint_set_r(expr[3])

    def _lint_fset_r(self, expr):
        if expr[0] == 'number':
            self.throw(f"Float literals are not supported")
        elif expr[0] == 'cast' and expr[1] != 'float':
            self.throw(f"Cannot cast to type '{expr[1]}' in 'fset' statement")
        elif expr[0] == 'operation':
            if expr[1] not in '+-*/':
                self.throw(f"'{expr[1]}' is not a valid float operation")
            self._lint_fset_r(expr[2])
            self._lint_fset_r(expr[3])

    def _lint_loadstore(self, op):
        def throw(msg):
            self.throw(f"Invalid '{op}' statement; {msg}")
        
        if op in ops.load_ops:
            expr = next(self.lexer)
            self.variables[expr[1]] = 'float' if op.startswith('lf') else 'int'
        else:
            expr = self._next_expression()

        if expr[0] != 'variable':
            self.throw(f"Invalid '{op}' statement")
        if op.startswith('st'):
            type_ = self.variables[expr[1]]
            type = 'float' if op.startswith('stf') else 'int'
            if type_ != type:
                self.throw(f"Cannot store '{type_}' variable using '{op}'")
        if next(self.lexer)[0] != ',':
            throw(f"missing ','")
        
        offset = self._next_expression()
        type_ = self._get_operand_type(offset)
        if offset[0] not in ['number', 'variable']:
            throw(f"offset cannot be of type '{offset[0]}'")
        elif type_ != 'int':
            throw(f"cannot use '{type_}' variable as offset")
        if next(self.lexer)[0] != '(':
            throw(f"missing '('")
        
        base = self._next_expression()
        type_ = self._get_operand_type(base)
        if base[0] != 'variable':
            throw(f"base cannot be of type '{base[0]}'")
        elif type_ != 'int':
            throw(f"cannot use '{type_}' variable as base")
        if next(self.lexer)[0] != ')':
            throw(f"missing ')'")

    # consumes token that triggered stop
    def _lint_block(self, stop_at):
        if next(self.lexer)[0] != ':':
            self.throw("Invalid block; missing ':'")
        if next(self.lexer)[0] != '\n':
            self.throw("Invalid block")
        # support both one and multiple stop_at keywords
        if type(stop_at) is str:
            stop_at = [stop_at]
        lines = []
        while self.lexer.next and not self.lexer.next[1] in stop_at:
            if self.lexer.next[0] == '\n':
                next(self.lexer)
            else:
                lines.append(self._lint_line())
        if not self.lexer.next:
            self.throw(f"Unclosed block")
        lines.append(next(self.lexer)[1])
        return lines

    def _lint_line(self):
        type_, token = next(self.lexer)
        if token == 'def':
            self.throw("Cannot define a function within a function")
        elif token == 'alloc':
            self._lint_alloc()
        elif token == 'call':
            self._lint_call()
        elif token in ['set', 'fset']:
            self._lint_set(token)
        elif token == 'switch':
            if self.in_switch:
                self.throw(f"Nested 'switch' statements are not supported")
            self._lint_switch()
        elif token == 'if':
            self._lint_if()
        elif token == 'for':
            if self.in_loop:
                self.throw(f"Nested loops are not supported")
            self._lint_for()
        elif token == 'while':
            if self.in_loop:
                self.throw(f"Nested loops are not supported")
            self._lint_while()
        elif type_ == 'load/store':
            self._lint_loadstore(token)
        elif token in ['break', 'continue']:
            if not self.in_loop:
                self.throw(f"Cannot use '{token}' outside of a loop")
        else:
            self.throw(f"Invalid statement")

        if next(self.lexer)[0] != '\n':
            self.throw(f"Invalid '{token}' statement")
        return token

    def throw(self, msg, line=None):
        if line is None:
            line = self.lexer.line
        fname = os.path.split(self.path)[1]
        sys.exit(f"[{fname}] {msg} (line {line})")
