import os, sys
from reader import Reader
from linter import Linter
from parser import Parser
from assembler import Assembler
from compiler import Compiler

def build(path, addr):
    os.chdir(os.path.dirname(path))
    name, ext = os.path.splitext(path)
    if ext != '.pbr':
        sys.exit(f"File must be of type '.pbr', not '{ext}'")
    if addr < 0x80000000 or addr > 0xffffffff:
        sys.exit(f"Address out of bounds")
    with Reader(path) as reader:
        linter = Linter(reader)
        print('Linting...')
        linter.lint()
        print('Done.')
    region = linter.region
    print('Parsing...')
    ast = []
    for path in linter.files:
        with Reader(path) as reader:
            parser = Parser(reader)
            ast += parser.parse()
    print('Done.')
    assembler = Assembler(region, addr, ast)
    asm = assembler.assemble()
    with open(f'{name}.asm', 'w+') as f:
        for line in asm:
            f.write(line + '\n')
    compiler = Compiler(addr, asm)
    bin = compiler.compile()
    with open(f'{name}.bin', 'wb+') as f:
        f.write(bin)
    print('Built successfully!')
##    print()
##    for line in asm:
##        print(f'{addr:08x} : {line}')
##        addr += 4
