load_ops = {'lbz', 'lbzu', 'lbzux', 'lbzx',
            'lfd', 'lfdu', 'lfdux', 'lfdx',
            'lfs', 'lfsu', 'lfsux', 'lfsx',
            'lha', 'lhau', 'lhaux', 'lhax',
            'lhz', 'lhzu', 'lhzux', 'lhzx',
            'lwz', 'lwzu', 'lwzux', 'lwzx'}

store_ops = {'stb', 'stbu', 'stbux', 'stbx',
             'stfd', 'stfdu', 'stfdux', 'stfdx',
             'stfs', 'stfsu', 'stfsux', 'stfsx',
             'sth', 'sthu', 'sthux', 'sthx',
             'stw', 'stwu', 'stwux', 'stwx'}

branch_ops = {'b', 'bctr', 'blt', 'ble', 'beq', 'bne', 'bgt', 'bge'}

compare_ops = {'cmplw', 'cmplwi', 'cmpw', 'cmpwi'}

math_ops = {'neg', 'and', 'andi.',
            'add', 'sub', 'mullw', 'divw',
            'addi', 'subi', 'mulli', 'rlwinm',
            'srw', 'srwi', 'slw', 'slwi',
            'fadds', 'fsubs', 'fmuls', 'fdivs', 'fctiwz'}
