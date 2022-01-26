import re

class Compiler:
    def __init__(self, addr, asm):
        self.address = addr
        self.asm = asm

    def compile(self):
        print('Compiling...')
        output = bytes()
        for line in self.asm:
            output += self._compile_line(line)
            self.address += 4
        print('Done.')
        return output

    def _compile_line(self, line):
        tokens = self._split_line(line)
        op = tokens[0]
        if op in ['add', 'sub', 'mullw', 'divw', 'neg']:
            return self._compile_math(tokens)
        elif op in ['addi', 'subi', 'mulli']:
            return self._compile_math_immediate(tokens)
        elif op in ['slw', 'srw']:
            return self._compile_shift(tokens)
        elif op in ['fadds', 'fdivs', 'fmuls', 'fsubs']:
            return self._compile_float_math(tokens)
        elif op == 'fctiwz':
            return self._compile_float_convert(tokens)
        elif op in ['rlwimi', 'rlwinm']:
            return self._compile_rotation(tokens)
        elif op in ['and', 'or', 'mr']:
            return self._compile_connective(tokens)
        elif op in ['cmpw', 'cmplw']:
            return self._compile_compare(tokens)
        elif op in ['cmpwi', 'cmplwi']:
            return self._compile_compare_immediate(tokens)
        elif op in ['fcmpo', 'fcmpu']:
            return self._compile_float_compare(tokens)
        elif op in ['lbz', 'lbzu', 'lfd', 'lfdu', 'lfs', 'lfsu',
                  'lha', 'lhau', 'lhz', 'lhzu', 'lwz', 'lwzu']:
            return self._compile_load(tokens)
        elif op in ['lbzx', 'lbzux', 'lhax', 'lhaux',
                    'lhzx', 'lhzux', 'lwzx', 'lwzux']:
            return self._compile_load_indexed(tokens)
        elif op in ['li', 'lis']:
            return self._compile_load_immediate(tokens)
        elif op in ['stb', 'stbu', 'stfd', 'stfdu', 'stfs', 'stfsu',
                    'sth', 'sthu', 'stw', 'stwu']:
            return self._compile_store(tokens)
        elif op in ['stbx', 'stbux', 'sthx', 'sthux']:
            return self._compile_store_indexed(tokens)
        elif op in ['b', 'bl']:
            return self._compile_branch(tokens)
        elif op in ['beq', 'bgt', 'bge', 'blt', 'ble', 'bne', 'bdnz']:
            return self._compile_branch_conditional(tokens)
        elif op in ['bctr', 'bctrl', 'blr']:
            return self._compile_branch_special(tokens)
        elif op in ['mfctr', 'mtctr', 'mflr', 'mtlr']:
            return self._compile_move_special(tokens)
        try:
            return int(op, 16).to_bytes(4, 'big')
        except:
            raise Exception(f'Unhandled: {op}')

    def _compile_math(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        A = int(tokens[2][1:])
        B = 0 if op == 'neg' else int(tokens[3][1:])
        if op == 'add':
            suffix = 266
        elif op == 'sub':
            suffix = 40
            A, B = (B, A)
        elif op == 'mullw':
            suffix = 235
        elif op == 'divw':
            suffix = 491
        elif op == 'neg':
            suffix = 104
        out = (31 << 26) + (D << 21) + (A << 16) + (B << 11) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_math_immediate(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        A = int(tokens[2][1:])
        SIMM = int(tokens[3], 16)
        if op.startswith('sub'):
            SIMM *= -1
        if op in ['addi', 'subi']:
            prefix = 14
        elif op == 'mulli':
            prefix = 7
        out = (prefix << 26) + (D << 21) + (A << 16) + (SIMM & 0xffff)
        return out.to_bytes(4, 'big')

    def _compile_float_math(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        A = int(tokens[2][1:])
        B = int(tokens[3][1:])
        C = 0
        if op == 'fadds':
            suffix = 21
        elif op == 'fdivs':
            suffix = 18
        elif op == 'fmuls':
            suffix = 25
            B, C = (C, B)
        elif op == 'fsubs':
            suffix = 20
        out = (59 << 26) + (D << 21) + (A << 16) + (B << 11) + (C << 6) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_float_convert(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        B = int(tokens[2][1:])
        out = (63 << 26) + (D << 21) + (B << 11) + (15 << 1)
        return out.to_bytes(4, 'big')

    def _compile_rotation(self, tokens):
        op = tokens[0]
        A = int(tokens[1][1:])
        S = int(tokens[2][1:])
        SH = int(tokens[3], 16)
        MB = int(tokens[4], 16)
        ME = int(tokens[5], 16)
        if op == 'rlwimi':
            prefix = 20
        elif op == 'rlwinm':
            prefix = 21
        out = (prefix << 26) + (S << 21) + (A << 16) + (SH << 11) \
              + (MB << 6) + (ME << 1)
        return out.to_bytes(4, 'big')

    def _compile_shift(self, tokens):
        op = tokens[0]
        S = int(tokens[1][1:])
        A = int(tokens[2][1:])
        B = int(tokens[3][1:])
        if op == 'slw':
            suffix = 24
        elif op == 'srw':
            suffix = 536
        out = (31 << 26) + (S << 21) + (A << 16) + (B << 11) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_connective(self, tokens):
        op = tokens[0]
        A = int(tokens[1][1:])
        S = int(tokens[2][1:])
        B = S if op == 'mr' else int(tokens[3][1:])
        if op == 'and':
            suffix = 28
        elif op in ['or', 'mr']:
            suffix = 444
        out = (31 << 26) + (S << 21) + (A << 16) + (B << 11) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_compare(self, tokens):
        op = tokens[0]
        A = int(tokens[1][1:])
        B = int(tokens[2][1:])
        if op == 'cmpw':
            suffix = 0
        elif op == 'cmplw':
            suffix = 32
        out = (31 << 26) + (A << 16) + (B << 11) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_compare_immediate(self, tokens):
        op = tokens[0]
        A = int(tokens[1][1:])
        IMM = int(tokens[2], 16)
        if op == 'cmpwi':
            prefix = 11
        elif op == 'cmplwi':
            prefix = 10
        out = (prefix << 26) + (A << 16) + (IMM & 0xffff)
        return out.to_bytes(4, 'big')

    def _compile_float_compare(self, tokens):
        op = tokens[0]
        D = int(tokens[1][2:])
        A = int(tokens[2][1:])
        B = int(tokens[3][1:])
        if op == 'fcmpo':
            suffix = 32
        elif op == 'fcmpu':
            suffix = 0
        out = (63 << 26) + (D << 23) + (A << 16) + (B << 11) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_load(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        A = int(tokens[3][1:])
        d = int(tokens[2], 16)
        if op.startswith('lbz'):
            prefix = 34
        elif op.startswith('lfd'):
            prefix = 50
        elif op.startswith('lfs'):
            prefix = 48
        elif op.startswith('lha'):
            prefix = 42
        elif op.startswith('lhz'):
            prefix = 40
        elif op.startswith('lwz'):
            prefix = 32
        if op[-1] == 'u':
            prefix += 1
        out = (prefix << 26) + (D << 21) + (A << 16) + (d & 0xffff)
        return out.to_bytes(4, 'big')

    def _compile_load_indexed(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        A = int(tokens[2][1:])
        B = int(tokens[3][1:])
        if op == 'lbzx':
            suffix = 87
        elif op == 'lhax':
            suffix = 343
        elif op == 'lhzx':
            suffix = 279
        elif op == 'lwzx':
            suffix = 23
        if op[-2] == 'u':
            suffix += 32
        out = (31 << 26) + (D << 21) + (A << 16) + (B << 11) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_load_immediate(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        # A = 0
        SIMM = int(tokens[2], 16)
        prefix = 14
        if op == 'lis':
            prefix += 1
        out = (prefix << 26) + (D << 21) + (SIMM & 0xffff)
        return out.to_bytes(4, 'big')
        
    def _compile_store(self, tokens):
        op = tokens[0]
        S = int(tokens[1][1:])
        A = int(tokens[3][1:])
        d = int(tokens[2], 16)
        if op.startswith('stb'):
            prefix = 38
        elif op.startswith('stfd'):
            prefix = 54
        elif op.startswith('stfs'):
            prefix = 52
        elif op.startswith('sth'):
            prefix = 44
        elif op.startswith('stw'):
            prefix = 36
        if op[-1] == 'u':
            prefix += 1
        out = (prefix << 26) + (S << 21) + (A << 16) + (d & 0xffff)
        return out.to_bytes(4, 'big')

    def _compile_store_indexed(self, tokens):
        op = tokens[0]
        S = int(tokens[1][1:])
        A = int(tokens[2][1:])
        B = int(tokens[3][1:])
        if op == 'stbx':
            suffix = 215
        elif op == 'sthx':
            suffix = 407
        if op[-2] == 'u':
            suffix += 32
        out = (31 << 26) + (S << 21) + (A << 16) + (B << 11) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _compile_branch(self, tokens):
        op = tokens[0]
        target = int(tokens[1], 16)
        LI = ((target - self.address) >> 2) & 0xffffff
        LK = 1 if op == 'bl' else 0
        out = (18 << 26) + (LI << 2) + LK
        return out.to_bytes(4, 'big')

    def _compile_branch_conditional(self, tokens):
        op = tokens[0]
        target = int(tokens[1], 16)
        BD = ((target - self.address) >> 2) & 0x3fff
        if op in ['beq', 'bgt', 'blt']:
            BO = 0b01100
        elif op in ['bge', 'ble', 'bne']:
            BO = 0b00100
        elif op == 'bdnz':
            BO = 0b10000
            
        if op in ['bge', 'blt', 'bdnz']:
            BI = 0
        elif op in ['bgt', 'ble']:
            BI = 1
        elif op in ['beq', 'bne']:
            BI = 2
        out = (16 << 26) + (BO << 21) + (BI << 16) + (BD << 2)
##        print(hex(target), hex(self.address))
##        print(f'{16:06b}|{BO:05b}|{BI:05b}|{BD:014b}|00')
##        print(f'{out:032b}')
##        raise Exception('Halt')
        return out.to_bytes(4, 'big')

    def _compile_branch_special(self, tokens):
        op = tokens[0]
        LK = 1 if op[-1] == 'l' else 0
        if op in ['bctr', 'bctrl', 'blr']:
            BO = 0b10100
        if op in ['bctr', 'bctrl', 'blr']:
            BI = 0
        if op in ['bctr', 'bctrl']:
            suffix = 528
        elif op == 'blr':
            suffix = 16
        out = (19 << 26) + (BO << 21) + (BI << 16) + (suffix << 1) + LK
        return out.to_bytes(4, 'big')

    def _compile_move_special(self, tokens):
        op = tokens[0]
        D = int(tokens[1][1:])
        suffix = 467 if op.startswith('mt') else 339
        if op.endswith('ctr'):
            spr = 9
        elif op.endswith('lr'):
            spr = 8
        out = (31 << 26) + (D << 21) + (spr << 16) + (suffix << 1)
        return out.to_bytes(4, 'big')

    def _split_line(self, line):
        tokens = re.split(r'[ ,(){}]+', line.strip())
        return list(filter(lambda x: x != '', tokens))
        

compiler = Compiler(0x8062b2b0, 'teambuilder.asm')
