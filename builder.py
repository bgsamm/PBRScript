import os
from reader import Reader
from linter import Linter
from parser import Parser
from assembler import Assembler
from compiler import Compiler

def build(path, addr):
    name, ext = os.path.splitext(path)
    if ext != '.pbr':
        raise Exception(f"File must be of type '.pbr', not '{ext}'")
    with Reader(path) as reader:
        linter = Linter(reader)
        linter.lint()
    with Reader(path) as reader:
        parser = Parser(reader)
        region, tree = parser.parse()
    assembler = Assembler(region, addr, tree)
    asm = assembler.assemble()
    with open(f'{name}.asm', 'w+') as f:
        for line in asm:
            f.write(line + '\n')
    compiler = Compiler(addr, asm)
    bin = compiler.compile()
    with open(f'{name}.bin', 'wb+') as f:
        f.write(bin)
##    compiler = Compiler(asm)
##    compiler.compile()
    print('Built successfully!')
##    print()
##    for line in asm:
##        print(f'{addr:08x} : {line}')
##        addr += 4
