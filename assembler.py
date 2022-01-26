import math, re
from data.classes import *
import data.pbr_globals as globals_
import data.ops as ops

op_to_asm = {
    '+': 'add',
    '-': 'sub',
    '*': 'mullw',
    '/': 'divw',
    'mask': 'and',
    'rshift': 'srw',
    'lshift': 'slw'
}

op_imm_to_asm = {
    '+': 'addi',
    '-': 'subi',
    '*': 'mulli',
    'mask': 'andi.',
    'rshift': 'srwi',
    'lshift': 'slwi'
    # no 'divi'
}

fop_to_asm = {
    '+': 'fadds',
    '-': 'fsubs',
    '*': 'fmuls',
    '/': 'fdivs',
}

inv_comps = {'eq': 'ne', 'ne': 'eq',
             'gt': 'le', 'ge': 'lt',
             'lt': 'ge', 'le': 'gt'}

var_pattern = r'@(INT|FLOAT)\(([_a-zA-Z0-9]+)\)'
branch_pattern = r'@BRANCH\(([0-9]+)\)'

def is_pow_of_two(n):
    x = math.log(n, 2)
    return x == int(x)

def is_mask_contiguous(mask):
    if mask & 0x80000000:
        mask = ~mask & 0xffffffff
    b = f'{mask:032b}'
    return re.search(r'10+1', b) is None

def get_mask_bounds(mask):
  b = f'{mask:032b}'
  if b.find('1') > 0 or b.rfind('1') < 31:
    return (b.find('1'), b.rfind('1'))
  return (b.rfind('0') + 1, b.find('0') - 1)

def split_op(op):
    args = re.split(r'@INT|@FLOAT|[ ,(){}]+', op)
    return [arg for arg in args if arg != '']

# "updates" = uses var being set as an arg as well
def op_sets_var(op, var, include_updates=True):
    args = split_op(op)
    return (args[0] in ops.load_ops \
            or args[0] in ops.math_ops \
            or args[0] in ['li', 'lis', 'fmr', 'mr']) \
            and args[1] == var \
            and (include_updates or var not in args[2:])

def is_call(op):
    return split_op(op)[0] in ['bl', 'bctrl']

def is_branch(op):
    return split_op(op)[0] in ops.branch_ops

def is_unconditional_branch(op):
    return split_op(op)[0] in ['b', 'bctr']

def is_move(op):
    return split_op(op)[0] in ['mr', 'fmr']

class Assembler:
    def __init__(self, region, addr, ast):
        self.region = region
        self.start_addr = addr
        self.syntax_tree = ast

    def assemble(self):
        print('Assembling...')
        asm = []
        self.functions = {}
        self.branch_idx = 0
        for node in self.syntax_tree:
            self.address = self.start_addr + 4 * len(asm)
            asm += self._assemble_node(node)
        # fill in function addresses
        for i in range(len(asm)):
            line = asm[i]
            if (match := re.search(r'(@|&)([_0-9a-zA-Z]+)', line)):
                name = match.group(2)
                addr = 0
                if name in self.functions:
                    addr = self.functions[name]
                elif name in globals_.functions[self.region]:
                    addr = globals_.functions[self.region][name]
                elif name.startswith('FUN_'):
                    addr = int(name[4:], 16)
                else:
                    print('UNKNOWN:', name)
                assert addr != 0
                if match.group(1) == '@':
                    asm[i] = line.replace(match.group(), hex(addr))
                else:
                    args = split_op(line)
                    assert args[0] == 'lis'
                    load = self._generate_load(addr)
                    asm[i] = load[0].replace('@INT(_temp_)', args[1])
                    asm[i+1] = load[1].replace('@INT(_temp_)', args[1])
        print('Done.')
        return asm

    def _assemble_node(self, node):
        if type(node) is Function:
            assert node.name not in self.functions
            self.functions[node.name] = self.address
            return self._assemble_def(node)
        elif type(node) is Call:
            return self._assemble_call(node)
        elif type(node) is Set:
            if node.type == 'float':
                return self._assemble_fset(node)
            else:
                return self._assemble_set(node)
        elif type(node) is LoadStore:
            return self._assemble_loadstore(node)
        elif type(node) is If:
            return self._assemble_if(node)
        elif type(node) is For:
            return self._assemble_for(node)
        elif type(node) is While:
            return self._assemble_while(node)
        elif type(node) is Switch:
            return self._assemble_switch(node)
        elif type(node) is Alloc:
            self.arrays[node.var.name] = {'type': node.type,
                                          'size': node.size}
            return []
        elif node[0] == 'break':
            return [f'b @BRANCH({self.break_idx})']
        elif node[0] == 'continue':
            return [f'b @BRANCH({self.continue_idx})']
        raise Exception(f"UNHANDLED NODE: '{node}'")

    def _assemble_def(self, node):
        # generate intermediate representation
        asm = []
        int_idx = 3
        float_idx = 1
        for param in node.params:
            if param.type == 'float':
                asm.append(f'fmr @FLOAT({param}), @FLOAT(_f{float_idx}_)')
                float_idx += 1
            else:
                asm.append(f'mr @INT({param}), @INT(_r{int_idx}_)')
                int_idx += 1
        self.arrays = {}
        self.switches = []
        self.casts = False
        for subnode in node.body:
            asm += self._assemble_node(subnode)
        if node.return_:
            if node.return_.type == 'float':
                asm.append(f'fmr @FLOAT(_f1_), @FLOAT({node.return_})')
            else:
                asm.append(f'mr @INT(_r3_), @INT({node.return_})')

        # allocate registers
        asm, num_ints, num_floats = self._alloc_persistent_registers(asm)
        asm = self._alloc_temp_registers(asm)
        asm = self._remove_redundancies(asm)

        # stack frames + return
        calls = any(is_call(line) for line in asm)
        arrays_size = sum(arr['size'] for arr in self.arrays.values())
        push, pop = self._make_stack_frame_commands(num_ints, num_floats,
                                                    arrays_size, calls,
                                                    self.casts)
        asm = push + asm + pop
        asm.append('blr')

        # set array addresses
        pattern = r'@ARRAY\(([_0-9a-zA-Z]+)(\[([0-9]+)\])*\)'
        for i in range(len(asm)):
            line = asm[i]
            offset = 0x10 if self.casts else 8
            if (match := re.search(pattern, line)):
                array = match.group(1)
                for arr in self.arrays:
                    if arr == array:
                        break
                    offset += 4 * self.arrays[arr]['size']
                if match.group(3):
                    offset += 4 * int(match.group(3))
                asm[i] = re.sub(pattern, hex(offset), line)

        # set branch addresses
        address = self.functions[node.name]
        branches = {}
        for i in range(len(asm)):
            if (match := re.match(branch_pattern, asm[i])):
                branch_idx = int(match.group(1))
                branches[branch_idx] = address + 4 * (i - len(branches))
        for i in range(len(asm) - 1, -1, -1):
            line = asm[i]
            # remove branch labels
            if re.match(branch_pattern, line):
                asm.pop(i)
            # fill placeholders
            elif (match := re.search(branch_pattern, line)):
                branch_idx = int(match.group(1))
                addr = branches[branch_idx]
                asm[i] = re.sub(branch_pattern, hex(addr), line)
            # strip @SWITCH tag from bctrs
            elif split_op(line)[0] == 'bctr':
                asm[i] = 'bctr'

        # build switch tables
        for i in range(len(asm)):
            if (match := re.search(r'@SWITCH_TABLE\(([0-9]+)\)', asm[i])):
                # update table address load
                table_addr = address + 4 * len(asm)
                reg = split_op(asm[i])[1]
                load = self._generate_load(table_addr)
                asm[i] = load[0].replace('@INT(_temp_)', reg)
                asm[i+1] = load[1].replace('@INT(_temp_)', reg)
                # make switch table
                idx = int(match.group(1))
                switch = self.switches[idx]
                for case in range(max(switch['cases']) + 1):
                    if case in switch['cases']:
                        branch_idx = switch['cases'][case]
                    else:
                        branch_idx = switch['default']
                    asm.append(hex(branches[branch_idx]))

        return asm

    def _remove_redundancies(self, asm):
        asm = asm[:]
        # remove redundant moves
        for i in range(len(asm) - 1, -1, -1):
            args = split_op(asm[i])
            if is_move(asm[i]) and args[1] == args[2]:
                asm.pop(i)
        # remove unnecessary param moves at start
        state = {}
        redundant = []
        for i in range(len(asm)):
            line = asm[i]
            if is_move(line):
                args = split_op(line)
                if args[2] in state and state[args[2]] == args[1]:
                    redundant.append(i)
                else:
                    state[args[1]] = args[2]
            elif is_call(line) or is_branch(line):
                break
            else:
                state = {k:v for k,v in state.items()
                         if not op_sets_var(line, v)
                         and not op_sets_var(line, k)}
        for i in redundant[::-1]:
            asm.pop(i)
        return asm

    def _make_stack_frame_commands(self, num_ints, num_floats,
                                   arrays_size, makes_call, makes_cast):
        push = []
        pop = []
        if num_ints + num_floats + arrays_size > 0 or makes_call or makes_cast:
            # floats need 4 words each; float->int casts use 2 words;
            # sp and lr need 1 word each
            count = num_ints + (num_floats * 4) + arrays_size \
                    + (2 if makes_cast else 0) + 2
            size = (count + 3) // 4 * 0x10
            # push stack frame
            push += [f'stwu r1, -{hex(size)}(r1)',
                     'mflr r0',
                     f'stw r0, {hex(size + 4)}(r1)']
            for i in range(num_floats):
                offset = size - 0x10 * (i + 1)
                push += [f'stfd f{31 - i}, {hex(offset)}(r1)',
                         f'psq_st p{31 - i}, {hex(offset + 8)}(r1), 0, qr0']
            if num_ints > 0:
                offset = size - 0x10 * num_floats
                push += [f'addi r11, r1, {hex(offset)}',
                         f'bl @FUN_{0x801cbd78 - 4 * num_ints:08x}']
            # pop stack frame
            for i in range(num_floats):
                offset = size - 0x10 * (i + 1)
                pop += [f'psq_l p{31 - i}, {hex(offset + 8)}(r1), 0, qr0',
                        f'lfd f{31 - 1}, {hex(offset)}(r1)']
            if num_ints > 0:
                offset = size - 0x10 * num_floats
                pop += [f'addi r11, r1, {hex(offset)}',
                        f'bl @FUN_{0x801cbdc4 - 4 * num_ints:08x}']
            pop += [f'lwz r0, {hex(size + 4)}(r1)',
                    'mtlr r0',
                    f'addi r1, r1, {hex(size)}']
        return push, pop

    # splits at branch labels
    def _make_basic_blocks(self, asm):
        blocks = []
        next_block = []
        for line in asm:
            if (match := re.match(branch_pattern, line)):
                blocks.append(next_block)
                next_block = []
            next_block.append(line)
        if len(next_block) > 0:
            blocks.append(next_block)
        return blocks

    def _make_control_flow_graph(self, blocks):
        # generate control flow graph
        graph = {}
        for i in range(len(blocks)):
            block = blocks[i]
            if (match := re.match(branch_pattern, block[0])):
                node = int(match.group(1))
            else:
                # entry point
                node = -1
            graph[node] = set()
            # branches
            for line in block:
                if line[0] != '@' and (match := re.search(branch_pattern, line)):
                    graph[node].add(int(match.group(1)))
                if (match := re.search(r'@SWITCH\(([0-9]+)\)', line)):
                    switch_idx = int(match.group(1))
                    graph[node].update(
                        self.switches[switch_idx]['cases'].values())
            # fall-through
            if i < len(blocks) - 1 \
               and split_op(block[-1])[0] not in ['b', 'bctr', 'blr']:
                match = re.match(branch_pattern, blocks[i+1][0])
                graph[node].add(int(match.group(1)))
        return graph

    def _alloc_persistent_registers(self, asm):
        variables = self._find_persistent_variables(asm)
        # assign persistent variables to registers
        registers = {}
        int_idx = 31
        float_idx = 31
        for var in variables:
            if variables[var] == 'float':
                if float_idx < 14:
                    raise Exception('Max. local floats exceeded')
                registers[var] = f'f{float_idx}'
                float_idx -= 1
            else:
                if int_idx < 14:
                    raise Exception('Max. local ints exceeded')
                registers[var] = f'r{int_idx}'
                int_idx -= 1
        # replace placeholders in assembly
        asm = asm[:]
        for i in range(len(asm)):
            vars = re.findall(var_pattern, asm[i])
            for type, name in vars:
                if name in registers:
                    asm[i] = re.sub(f'@{type}\({name}\)', registers[name],
                                    asm[i])
        # count int vs float registers
        num_ints = sum(1 for reg in registers.values() if reg[0] == 'r')
        num_floats = len(registers) - num_ints
        return asm, num_ints, num_floats

    def _find_persistent_variables(self, asm):
        if len(asm) == 0:
            return {}
        blocks = self._make_basic_blocks(asm)
        cfg = self._make_control_flow_graph(blocks)
        return self._find_persistent_variables_r(blocks, cfg, {}, {}, -1)

    def _find_persistent_variables_r(self, blocks, cfg, states, visited, index):
        block = self._get_block_from_branch_index(blocks, index)
        persistent = {}
        for line in block:
            # this pattern intentionally ignores
            # generated variables (those bookended by _)
            pattern = r'@(INT|FLOAT)\(([a-z][_a-zA-Z0-9]*)\)'
            vars = re.findall(pattern, line)
            for type, name in vars:
                if op_sets_var(line, name, False) or states[name]:
                    states[name] = True # "fresh"
                else:
                    persistent[name] = type.lower()
            if is_call(line):
                for name in states:
                    states[name] = False # "stale"
        if index not in visited:
            visited[index] = 0
        else:
            visited[index] += 1
        # only traverse loops twice
        if visited[index] == 1 and \
           all(edge not in visited or visited[edge] == 1
               for edge in cfg[index]):
            return persistent
        for edge in cfg[index]:
            if edge in visited and visited[edge] == 1:
                continue
            persistent.update(
                self._find_persistent_variables_r(blocks, cfg, states.copy(),
                                                  visited.copy(), edge))
        return persistent

    def _get_block_from_branch_index(self, blocks, index):
        if index == -1:
            return blocks[0]
        for block in blocks:
            if block[0] == f'@BRANCH({index})':
                return block
        raise Exception(f"No block exists with branch index '{index}'")

    def _alloc_temp_registers(self, asm):
        asm = asm[:]
        groups = self._group_lines(asm)
        for group in groups:
            graph = self._make_interference_graph(asm, group)
            block = [line for i,line in enumerate(asm) if i in group]
            regs = self._assign_temp_registers(graph, block)
            # replace placeholders in assembly
            for i in group:
                vars = re.findall(var_pattern, asm[i])
                for type, name in vars:
                    asm[i] = re.sub(f'@{type}\({name}\)', regs[name], asm[i])
        return asm

    # groups connected sections of code, i.e. lines
    # of code that are not separated by calls
    def _group_lines(self, asm):
        lines_left = set(range(len(asm)))
        groups = []
        while len(lines_left) > 0:
            next_line = min(lines_left)
            group = self._group_lines_r(asm, set(), next_line)
            # get index of first non-empty intersection, if any
            idx = next((i for i,n in enumerate(g & group for g in groups)
                        if n != set()), None)
            if idx is not None:
                # merge overlapping groups
                groups[idx] |= group
            else:
                groups.append(group)
            lines_left -= group
        return groups

    def _group_lines_r(self, asm, group, line_num):
        for i in range(line_num, len(asm)):
            if i in group:
                break
            group.add(i)
            line = asm[i]
            if is_branch(line):
                match = re.search(r'@(BRANCH|SWITCH)\(([0-9]+)\)', line)
                if match.group(1) == 'SWITCH':
                    idx = int(match.group(2))
                    for branch in self.switches[idx]['cases'].values():
                        line_num = asm.index(f'@BRANCH({branch})')
                        self._group_lines_r(asm, group, line_num)
                else:
                    line_num = asm.index(f'@BRANCH({match.group(2)})')
                    self._group_lines_r(asm, group, line_num)
            if split_op(line)[0] == 'b' or is_call(line):
                break
        return group

    def _make_interference_graph(self, asm, group):
        unvisited = group.copy()
        graph = {}
        while unvisited:
            visited = self._make_interference_graph_r(asm, group, max(unvisited),
                                                      set(), graph)
            unvisited -= visited
        return graph

    def _make_interference_graph_r(self, asm, group, start, live, graph, loop=False):
        visited = set()
        i = start
        while not (branch := re.match(branch_pattern, asm[i])):
            line = asm[i]
            vars = re.findall(var_pattern, line)
            for type, name in vars:
                if name not in graph:
                    graph[name] = { 'edges': set(), 'type': type.lower() }
                if op_sets_var(line, name):
                    # handles variables unused after being set
                    for var in live:
                        if var != name:
                            graph[var]['edges'].add(name)
                            graph[name]['edges'].add(var)
                    if op_sets_var(line, name, False):
                        live.discard(name)
                    else:
                        live.add(name)
                else:
                    live.add(name)
            for var in live:
                graph[var]['edges'] = graph[var]['edges'] | (live - {var})
            # reset 'live' after call & initialize with function params
            if is_call(line):
                live = set()
                j = i - 1
                while (match := re.search('_([fr])[0-9]+_', asm[j])):
                    name = match.group()
                    type = 'float' if match.group(1) == 'f' else 'int'
                    live.add(name)
                    graph[name] = { 'edges': set(), 'type': type }
                    j -= 1
            visited.add(i)
            if (i-1) not in group or is_unconditional_branch(asm[i-1]):
                break
            i -= 1
        end = i
        visited.add(end)
        # fall-through
        if end - 1 in group and not is_unconditional_branch(asm[end-1]):
            visited |= self._make_interference_graph_r(asm, group, end - 1,
                                                       live.copy(), graph, loop)
        # branching
        if branch:
            for i in group:
                line = asm[i]
                if (switch := re.search(r'@SWITCH\(([0-9]+)\)', line)):
                    switch_idx = int(switch.group(1))
                    branch_idx = int(branch.group(1))
                    if branch_idx in self.switches[switch_idx]['cases'].values():
                        visited |= self._make_interference_graph_r(asm, group, i,
                                                                   live.copy(),
                                                                   graph, loop)
                elif line[0] != '@' and f'@BRANCH({branch.group(1)})' in line:
                    if i > end:
                        if loop:
                            continue
                        loop = True
                    visited |= self._make_interference_graph_r(asm, group, i,
                                                               live.copy(),
                                                               graph, loop)
        return visited

    def _assign_temp_registers(self, graph, block):
        registers = {}
        for var in graph:
            # pre-color function args
            if (match := re.match('_([fr][0-9]+)_', var)):
                registers[var] = match.group(1)
        for var in filter(lambda x : x not in registers, graph):
            if graph[var]['type'] == 'float':
                regs = [f'f{n}' for n in range(14)]
            else:
                regs = [f'r{n}' for n in range(3, 13)]
            # some commands break w/ r0; make sure var
            # is a valid candidate for its use
            if graph[var]['type'] == 'int' \
               and self._can_var_use_r0(var, block):
                regs.insert(0, 'r0')
            for edge in graph[var]['edges']:
                if edge in registers and registers[edge] in regs:
                    regs.remove(registers[edge])
            # try to assign so as to reduce moves
            for line in block:
                args = split_op(line)
                if is_move(line) and var in args:
                    copy_var = args[1] if args[1] != var else args[2]
                    if copy_var in registers \
                       and registers[copy_var] in regs:
                        registers[var] = registers[copy_var]
                        break
            # if no way to reduce moves, use first available register
            if var not in registers:
                registers[var] = regs[0]
        return registers

    def _can_var_use_r0(self, var, block):
        for line in block:
            args = split_op(line)
            if args[0] in {'addi', 'subi'} and args[2] == var:
                return False
            elif args[0] in ops.load_ops | ops.store_ops:
                if args[0][-1] == 'x' and args[2] == var:
                    return False
                elif args[3] == var:
                    return False
        return True

    def _assemble_if(self, node):
        asm = []
        end_idx = self.next_branch_index()
        next_idx = end_idx
        for i in range(len(node.blocks) - 1, -1, -1):
            block = []
            for line in node.blocks[i][1]:
                block += self._assemble_node(line)
            if i < len(node.blocks) - 1:
                block.append(f'b @BRANCH({end_idx})')
            if node.blocks[i][0] is not None:
                body_idx = self.next_branch_index()
                condition = self._assemble_condition(node.blocks[i][0],
                                                     body_idx,
                                                     next_idx)
                block = condition + [f'@BRANCH({body_idx})'] + block
            if i > 0:
                next_idx = self.next_branch_index()
                block.insert(0, f'@BRANCH({next_idx})')
            asm = block + asm
        return asm + [f'@BRANCH({end_idx})']

    def _assemble_condition(self, node, true_idx, false_idx):
        asm = []
        if type(node) is CompoundConditional:
            asm += self._assemble_comparison(node.left)
            if node.connective == 'and':
                comp = inv_comps[node.left.comparator]
                asm.append(f'b{comp} @BRANCH({false_idx})')
            else:
                comp = node.left.comparator
                asm.append(f'b{comp} @BRANCH({true_idx})')
            node = node.right
        asm += self._assemble_comparison(node) \
               + [f'b{inv_comps[node.comparator]} @BRANCH({false_idx})']
        return asm

    def _assemble_comparison(self, node):
        asm = []
        if type(node.left) is not Variable:
            arg1 = '_temp_'
            asm += self._generate_math(node.left, arg1)
        else:
            arg1 = node.left
        if type(node.right) is Number:
            # cmpwi will treat a number > 0x7fff as negative
            op = 'cmpwi' if node.right.value < 0x8000 else 'cmplwi'
            # floats cannot be compared with literals
            asm.append(f'{op} @INT({arg1}), {node.right}')
        else:
            op = 'fcmpu cr0,' if node.type == 'float' else 'cmpw'
            type_ = node.type.upper()
            asm.append(f'{op} @{type_}({arg1}), @{type_}({node.right})')
        return asm

    def _assemble_for(self, node):
        self.continue_idx = self.next_branch_index()
        self.break_idx = self.next_branch_index()
        body_idx = self.next_branch_index()
        asm = [f'li @INT({node.var}), 0x0',
               f'@BRANCH({body_idx})']
        for line in node.body:
            asm += self._assemble_node(line)
        asm += [f'@BRANCH({self.continue_idx})',
                f'addi @INT({node.var}), @INT({node.var}), 0x1']
        if type(node.range) is Variable:
            asm.append(f'cmpw @INT({node.var}), @INT({node.range})')
        else:
            asm.append(f'cmpwi @INT({node.var}), {node.range}')
        asm += [f'blt @BRANCH({body_idx})',
                f'@BRANCH({self.break_idx})']
        return asm

    def _assemble_while(self, node):
        self.continue_idx = self.next_branch_index()
        self.break_idx = self.next_branch_index()
        body_idx = self.next_branch_index()
        asm = [f'@BRANCH({self.continue_idx})']
        asm += self._assemble_condition(node.condition, body_idx,
                                        self.break_idx)
        asm.append(f'@BRANCH({body_idx})')
        for line in node.body:
            asm += self._assemble_node(line)
        asm += [f'b @BRANCH({self.continue_idx})',
                f'@BRANCH({self.break_idx})']
        return asm

    def _assemble_switch(self, node):
        asm = []
        switch = {'cases': {}, 'default': -1}
        exit_idx = self.next_branch_index()
        default_idx = exit_idx
        for i in range(len(node.blocks)):
            block = []
            if len(node.blocks[i].cases) == 0:
                default_idx = self.next_branch_index()
                block += [f'@BRANCH({default_idx})']
            else:
                for case in node.blocks[i].cases:
                    branch_idx = self.next_branch_index()
                    block.append(f'@BRANCH({branch_idx})')
                    switch['cases'][case] = branch_idx
            for line in node.blocks[i].body:
                block += self._assemble_node(line)
            if i < len(node.blocks) - 1:
                block.append(f'b @BRANCH({exit_idx})')
            asm += block
        switch['default'] = default_idx
        switch_idx = len(self.switches)
        max_case = max(switch['cases'])
        asm = [f'cmplwi @INT({node.var}), {hex(max_case)}',
               f'bgt @BRANCH({default_idx})',
               f'lis @INT(_addr_), @SWITCH_TABLE({switch_idx})',
               f'addi @INT(_addr_), @INT(_addr_), @SWITCH_TABLE({switch_idx})',
               f'rlwinm @INT(_offset_), @INT({node.var}), 0x2, 0x0, 0x1d',
               f'lwzx @INT(_addr_), @INT(_addr_), @INT(_offset_)',
               f'mtctr @INT(_addr_)',
               f'bctr @SWITCH({switch_idx})'] + asm + [f'@BRANCH({exit_idx})']
        self.switches.append(switch)
        return asm

    def _assemble_call(self, node):
        asm = []
        int_idx = 3
        float_idx = 1
        for i in range(len(node.args)):
            arg = node.args[i]
            if type(arg) is Variable and arg.type == 'float':
                name = f'_f{float_idx}_'
            else:
                name = f'_r{int_idx}_'
            if type(arg) is Number:
                load = self._generate_load(arg.value, name=name)
                asm += load
            elif type(arg) is Variable:
                if arg.type == 'float':
                    asm.append(f'fmr @FLOAT({name}), @FLOAT({arg})')
                else:
                    asm.append(f'mr @INT({name}), @INT({arg})')
            elif type(arg) is Pointer:
                if arg.type == 'array':
                    asm.append(f'addi @INT({name}), r1, @ARRAY({arg})')
                else:
                    asm.append(f'lis @INT({name}), &{arg}')
                    asm.append(f'addi @INT({name}), @INT({name}), &{arg}')
            else:
                raise Exception(f'UNHANDLED ARGUMENT: {arg}')
            if type(arg) is Variable and arg.type == 'float':
                float_idx += 1
            else:
                int_idx += 1
        if node.type is Pointer:
            asm += [f'mtctr @INT({node.function})',
                    f'bctrl']
        else:
            asm.append(f'bl @{node.function}')
        return asm

    def _assemble_set(self, node):
        if type(node) is Array:
            name = '_temp_'
            handled = False
        else:
            name = node.var.name
        asm = []
        if type(node.expression) is Number:
            load = self._generate_load(node.expression.value, name=name)
            asm += load
        elif type(node.expression) is Variable:
            if type(node.var) is Array:
                asm.append(f'stw @INT({node.expression}), @ARRAY({node.var}[{node.var.index}])(r1)')
                handled = True
            else:
                asm.append(f'mr @INT({name}), @INT({node.expression})')
        elif type(node.expression) is Array:
            asm.append(f'lwz @INT({name}), @ARRAY({node.expression}[{node.expression.index}])(r1)')
        elif type(node.expression) is Pointer:
            if node.expression.type == 'array':
                asm.append(f'addi @INT({name}), r1, @ARRAY({arg})')
            else:
                # placeholders
                asm.append(f'lis @INT({name}), &{node.expression}')
                asm.append(f'addi @INT({name}), @INT({name}), &{node.expression}')
        elif type(node.expression) is Cast:
            asm += [f'fctiwz @FLOAT(_ftemp_), @FLOAT({node.expression.var})',
                    f'stfd @FLOAT(_ftemp_), 0x8(r1)',
                    f'lwz @INT({name}), 0xc(r1)']
            self.casts = True
        elif type(node.expression) is Call:
            asm += self._assemble_call(node.expression)
            if type(node.var) is Array:
                asm.append(f'stw @INT(_r3_), @ARRAY({node.var}[{node.var.index}])(r1)')
                handled = True
            else:
                asm.append(f'mr @INT({name}), @INT(_r3_)')
        else:
            asm += self._generate_math(node.expression, f'{name}')
        if type(node.var) is Array and not handled:
            asm.append(f'stw @INT({name}), @ARRAY({node.var}[{node.var.index}])(r1)')
        return asm

    def _assemble_fset(self, node):
        if type(node.var) is Array:
            name = '_ftemp_'
            handled = False
        else:
            name = node.var.name
        asm = []
        if type(node.expression) is Variable:
            if type(node.var) is Array:
                asm.append(f'stfs @FLOAT({node.expression}), @ARRAY({node.var}[{node.var.index}])(r1)')
                handled = True
            else:
                asm.append(f'fmr @FLOAT({name}), @FLOAT({node.expression})')
        elif type(node.expression) is Array:
            asm.append(f'lfs @FLOAT({name}), @ARRAY({node.expression}[{node.expression.index}])(r1)')
        elif type(node.expression) is Cast:
            asm += [f'lis @INT(_temp_), 0x4330',
                    f'stw @INT(_temp_), 0x8(r1)',
                    f'stw @INT({node.expression.var}), 0xc(r1)',
                    f'lfd @FLOAT({name}), 0x8(r1)',
                    f'lfd @FLOAT(_ftemp_), -0x7ff8(r2)', # 4330000000000000h
                    f'fsubs @FLOAT({name}), @FLOAT({name}), @FLOAT(_ftemp_)']
            self.casts = True
        elif type(node.expression) is Call:
            asm += self._assemble_call(node.expression)
            if type(node.var) is Array:
                asm.append(f'stfs @FLOAT(_f1_), @ARRAY({node.var}[{node.var.index}])(r1)')
                handled = True
            else:
                asm.append(f'fmr @FLOAT({name}), @FLOAT(_f1_)')
        else:
            asm += self._generate_fmath(node.expression, f'{name}')
        if type(node.var) is Array and not handled:
            asm.append(f'stfs @FLOAT({name}), @ARRAY({node.var}[{node.var.index}])(r1)')
        return asm

    def _assemble_loadstore(self, node):
        if type(node.offset) is Number:
            return [f'{node.opcode} @{node.type.upper()}({node.var}), {node.offset}(@INT({node.base}))']
        else:
            return [f'{node.opcode}x @{node.type.upper()}({node.var}), @INT({node.base}), @INT({node.offset})']

    def _generate_load(self, value, name='_temp_'):
        asm = []
        if value > 0xffff:
            upper = value >> 0x10
            lower = value & 0xffff
            if lower & 0x8000 != 0:
              upper += 1
            if upper & 0x8000 != 0:
              asm.append(f'lis @INT({name}), -{hex(-upper & 0xffff)}')
            else:
              asm.append(f'lis @INT({name}), {hex(upper)}')
            if lower & 0x8000 != 0:
              asm.append(f'subi @INT({name}), @INT({name}), {hex(-lower & 0xffff)}')
            elif lower > 0:
              asm.append(f'addi @INT({name}), @INT({name}), {hex(lower)}')
        elif value > 0x7fff:
            asm.append(f'lis @INT({name}), 0x1')
            asm.append(f'subi @INT({name}), @INT({name}), {hex(0x10000 - value)}')
        else:
            asm.append(f'li @INT({name}), {hex(value)}')
        return asm

    def _generate_math(self, op, dest, n=0):
        asm = []
        if op.operator == 'insert':
            if type(op.left.left) is Number:
                nameL = f'_temp{n}_'
                asm += self._generate_load(op.left.left.value, name=nameL)
                n += 1
            else:
                nameL = op.left.left.name
            mask = op.left.right.value
            if type(op.right) is Number:
                nameR = f'_temp{n}_'
                asm += self._generate_load(op.right.value, name=nameR)
            else:
                nameR = op.right.name
            if not is_mask_contiguous(mask):
                raise Exception(f"Non-contiguous insertion mask '{hex(mask)}'")
            start, end = get_mask_bounds(mask)
            size = end - start + 1 if end > start else 0x21 + end - start
            asm += [f'mr @INT(_temp{n}_), @INT({nameL})',
                    f'rlwimi @INT(_temp{n}_), @INT({nameR}), ' + \
                    f'{hex((0x40 - start - size) % 0x20)}, {hex(start)}, ' + \
                    f'{hex((start + size - 1) % 0x20)}',
                    f'mr @INT({dest}), @INT(_temp{n}_)']
            return asm
        elif op.operator == 'mod':
            mod = Operation('-', op.left,
                            Operation('*', Operation('/', op.left,op.right),
                                      op.right))
            return self._generate_math(mod, dest, n)
        vars = []
        for arg in [op.left, op.right]:
            temp = f'_temp{n}_'
            if type(arg) is Variable:
                vars.append(arg.name)
            elif type(arg) is Array:
                asm.append(f'lwz @INT({temp}), @ARRAY({arg}[{arg.index}])(r1)')
                vars.append(temp)
                n += 1
            elif type(arg) is Cast:
                asm += [f'fctiwz @FLOAT(_ftemp_), @FLOAT({arg.var})',
                        f'stfd @FLOAT(_ftemp_), 0x8(r1)',
                        f'lwz @INT({temp}), 0xc(r1)']
                self.casts = True
                vars.append(temp)
                n+= 1
            elif type(arg) is Number:
                if (arg.value > 0x7fff and (op.operator != 'mask' \
                                            or not is_mask_contiguous(arg.value))) \
                   or (op.operator in ['/', 'rshift', 'lshift'] and type(op.left) is Number) \
                   or (op.operator == '/' and not is_pow_of_two(arg.value)):
                    asm += self._generate_load(arg.value, name=temp)
                    vars.append(temp)
                    n += 1
                else:
                    const = arg.value
            else: # operation
                asm += self._generate_math(arg, temp, n)
                vars.append(temp)
                n += 1
        if len(vars) == 2:
            op = op_to_asm[op.operator]
            asm.append(f'{op} @INT({dest}), @INT({vars[0]}), @INT({vars[1]})')
        elif len(vars) == 1:
            if op.operator == '/':
                shift = 0x20 - int(math.log(const, 2))
                asm.append(f'rlwinm @INT({dest}), @INT({vars[0]}), {hex(shift)}, {hex(0x20 - shift)}, 0x1f')
            # I assume rlwinm is faster than mulli, otherwise this is unneeded
            elif op.operator == '*' and is_pow_of_two(const):
                shift = int(math.log(const, 2))
                asm.append(f'rlwinm @INT({dest}), @INT({vars[0]}), {hex(shift)}, 0x0, {hex(0x1f - shift)}')
            elif op.operator == '-' and type(op.left) is Number:
                # not 100% sure it's kosher to hard-code temp here
                asm.append(f'neg @INT(_temp_), @INT({vars[0]})')
                asm.append(f'addi @INT({dest}), @INT(_temp_), {hex(const)}')
            elif op.operator == 'mask' and is_mask_contiguous(const):
                start, end = get_mask_bounds(const)
                asm.append(f'rlwinm @INT({dest}), @INT({vars[0]}), 0x0, {hex(start)}, {hex(end)}')
            elif op.operator in ['rshift', 'lshift'] \
                 and len(asm) > 0 and asm[-1].startswith('rlwinm'):
                args = split_op(asm[-1])
                start = int(args[4], 16)
                end = int(args[5], 16)
                # needs some error checking
                if op.operator == 'lshift':
                    rot = const
                    start = max(start - const, 0)
                    end = max(end - const, 0)
                else:
                    rot = 32 - const
                    start = min(start + const, 31)
                    end = min(end + const, 31)
                asm[-1] = f'rlwinm @INT({dest}), @INT({args[2]}), {hex(rot)}, {hex(start)}, {hex(end)}'
            else:
                op = op_imm_to_asm[op.operator]
                asm.append(f'{op} @INT({dest}), @INT({vars[0]}), {hex(const)}')
        else:
            print(op)
            raise Exception(f"Cannot operate between two literals")
        return asm

    def _generate_fmath(self, op, dest, n=0):
        asm = []
        vars = []
        for arg in [op.left, op.right]:
            temp = f'_temp{n}_'
            if type(arg) is Variable:
                vars.append(arg.name)
            elif type(arg) is Array:
                asm.append(f'lfs @FLOAT({temp}), @ARRAY({arg}[{arg.index}])')
                vars.append(temp)
                n += 1
            elif type(arg) is Cast:
                asm += [f'lis @INT(_temp_), 0x4330',
                        f'stw @INT(_temp_), 0x8(r1)',
                        f'stw @INT({arg.var}), 0xc(r1)',
                        f'lfd @FLOAT({temp}), 0x8(r1)',
                        f'lfd @FLOAT(_ftemp_), -0x7ff8(r2)',
                        f'fsubs @FLOAT({temp}), @FLOAT({temp}), @FLOAT(_ftemp_)']
                self.casts = True
                vars.append(temp)
                n += 1
            else: # operation
                asm += self._generate_fmath(arg, temp, n)
                vars.append(temp)
                n += 1
        op = fop_to_asm[op.operator]
        asm.append(f'{op} @FLOAT({dest}), @FLOAT({vars[0]}), @FLOAT({vars[1]})')
        return asm

    def next_branch_index(self):
        idx = self.branch_idx
        self.branch_idx += 1
        return idx
