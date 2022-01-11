class Number:
    def __init__(self, value):
        self.value = value
        self.type = 'int'

    def __str__(self):
        return hex(self.value)

class Variable:
    def __init__(self, name, type):
        self.name = name
        self.type = type

    def __str__(self):
        return self.name

class Array:
    def __init__(self, name, type, index):
        self.name = name
        self.type = type
        self.index = index

    def __str__(self):
        return self.name

class Pointer:
    def __init__(self, target, type):
        self.target = target
        self.type = type

    def __str__(self):
        return self.target

class Cast:
    def __init__(self, var, to):
        self.var = var
        self.type = to

class Operation:
    def __init__(self, op, left, right):
        self.operator = op
        self.left = left
        self.right = right

        assert left.type == right.type
        self.type = left.type

class Conditional:
    def __init__(self, op, left, right):
        self.comparator = op
        self.left = left
        self.right = right
        
        assert left.type == right.type
        self.type = left.type

class CompoundConditional:
    def __init__(self, op, left, right):
        self.connective = op
        self.left = left
        self.right = right

class Alloc:
    def __init__(self, name, type, size):
        self.var = name
        self.type = type
        self.size = size

class LoadStore:
    def __init__(self, op, var, base, offset):
        self.opcode = op
        self.var = var
        self.base = base
        self.offset = offset
        self.type = 'float' if 'f' in op else 'int'

class Set:
    def __init__(self, type, var, expr):
        self.type = type
        self.var = var
        self.expression = expr

class Call:
    def __init__(self, func, args, type):
        self.function = func
        self.args = args
        self.type = type

class Function:
    def __init__(self, name, params, body, return_):
        self.name = name
        self.params = params
        self.body = body
        self.return_ = return_

    def __str__(self):
        return self.name

class Switch:
    def __init__(self, var, blocks):
        self.var = var
        self.blocks = blocks

class Case:
    def __init__(self, cases, body):
        self.cases = cases
        self.body = body

class If:
    def __init__(self, blocks):
        self.blocks = blocks

class For:
    def __init__(self, var, count, body):
        self.var = var
        self.range = count
        self.body = body

class While:
    def __init__(self, condition, body):
        self.condition = condition
        self.body = body
