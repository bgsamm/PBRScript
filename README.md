# What is PBRScript?
PBRScript is a scripting language designed to simplify the process of extending Pokémon Battle Revolution's code. PBRScript provides a high-level syntax for implementing new game logic while still allowing for direct interaction with the game's existing assembly.

# PBRScript Syntax

Jump links: [Comments](#comments) | [Function definitions](#function-definitions) | [Variable assignment](#variable-assignment) | [Array allocation](#array-allocation) | [Pointer](#pointers) | [Expressions](#expressions) | [Conditions](#conditions) | [Function calls](#function-calls) | [If-Elif-Else blocks](#if-elif-else-blocks) | [For loops](#for-loops) | [While loops](#while-loops) | [Switch blocks](#switch-blocks) | [Memory Reading/Writing](#memory-readingwriting)

### Comments
```
// this is a comment
```
Comments are preceded by `//` followed by a space. They may appear at the end of lines or stand alone on their own line.

### Function definitions
```
def FOO(int <intParam>, float <floatParam>):
  // function body
return <returnValue>
```
Functions are defined using the `def` keyword, followed by a function name and a list of comma-separated parameters in parentheses. Parameters should be preceded by either the `int` or `float` keywords to indicate the type of the incoming parameter. Function definitions end with the `return` keyword, which may optionally be followed by a variable to be returned by the function. 

**Note:** function names *must* begin with an upper-case letter and can contain a combination of numbers, letters, and underscores.

### Variable assignment
```
set <intVar> = <expression>
fset <floatVar> = <expression>
```
Values may be assigned to variables using the keyword `set` (for int variables) or `fset` (for float variables). See the [Expressions](#expressions) section for more information on what may appear on the right side of a `set`/`fset` statement.

**Note:** variable names *must* begin with a lower-case letter and can contain a combination of numbers, letters, and underscores.

### Array allocation
```
alloc <arrayName> = (int|float)[<size>]
(set|fset) <arrayName>[<index>] = <expression>
```
Arrays are defined using the `alloc` keyword, followed by a name for the array and a `=` symbol. On the right of the `=` symbol should be a type keyword (`int` or `float`) followed by the size of the array in square brackets (e.g. `int[10]`, `float[8]`). Array elements can be accessed or assigned to the array name followed by the zero-based index of the element in square brackets (e.g. `my_array[0]`).

**Note:** array names follow the same rules as variable names (see above).

### Pointers
```
&<variable|function|array>
```
Pointers can be created by prepending a function or variable/array name with a `&` symbol. This can be used to pass array and function references as arguments to calls. Function pointers can also be assigned to variables, in which case the variable can be used as the target of a call itself (e.g. `call &<variable>(...)`).

### Expressions
```
<var1> + 2 * <var2>
<var1> mask 0x3f0 insert <var2>
```
Expressions consist of a string of variables and numbers connected by mathematical operations. Beyond the basic arithmetic operations `+`, `-`, `*`, and `/`, the following `int`-only operations are avaiable.
| Symbol | Description |
| ------ | ----------- |
| `mod`  | modular division |
| `mask` | bitwise "and" |
| `lshift` | left bit-shift |
| `rshift` | right bit-shift |
| `insert` | when combined with `mask`, inserts bits at a given position in a number or variable |

#### Casts
```
((int|float))<variable>
```
Variables can be cast between `int` and `float` types by preceding the variable name with the desired type in parentheses.

### Conditions
```
<a> gt <b> and <c> le <d>
<a> eq <b> or <c> ne <d>
```
Conditions are used in `if`, `elif`, and `while` constructs. They consist of a comparison followed optionally by either the `and` or `or` keywords and a second comparison. Comparisons are of the form `<expr1> <mnemonic> <expr2>`. See the [Expressions](#expressions) section for more information on the expressions that can appear inside conditions.

The list of mnemonics available for use in comparisons are listed in the following table.
| Mnemonic | Name |
| -------- | ---- |
| `eq`     | equal |
| `ne`     | not equal |
| `gt`     | greater than |
| `ge`     | greater than or equal |
| `lt`     | less than |
| `le`     | less than or equal |

### Function calls
```
call <FUNCTION_NAME>(<param1>, <param2>, ...)
```
Functions can be called using the `call` keyword, followed by the function name and a list of comma-separated arguments. Arguments can be variables, numbers, or pointers.

### If-Elif-Else blocks
```
if <condition>:
  // do something
elif <condition>:
  // do something
else:
  // do something
end
```
An `if-elif-else` block consists of an `if` statement, any number of optional `elif` statements, an optional `else` statement, and a terminating `end` keyword. See the [Conditions](#conditions) section for more information on the conditions that can be used with `if`/`elif` blocks.

### For loops
```
for <var> in range(<count>):
  // do something
end
```
A `for` block consists of the `for` keyword, an iterand variable, the `in` keyword, and a `range` whose argument must be either a number or a variable. The same variable cannot be used both as the iterand and the argument to `range`. The block is terminated by the `end` keyword. The `break` and `continue` keywords can be used to exit a loop or skip to the next iteration, respectively.

**Note:** nested loops are not currently supported.

### While loops
```
while <condition>:
  // do something
end
```
A `while` block consists of the `while` keyword followed by a conditional statement. See the [Conditions](#conditions) section for more information on the conditions that can be used with `while` blocks. The block is terminated by the `end` keyword. The `break` and `continue` keywords can be used to exit a loop or skip to the next iteration, respectively.

**Note:** nested loops are not currently supported.

### Switch blocks
```
switch <var>:
  case <val1>:
    // do something
    break
  case <val2>:
  case <val3>:
    // do something
    break
  default:
    // do something
    break
end
```
A `switch` block consists of the `switch` keyword followed by a variable to switch on. A `switch` can contain any number of `case` blocks along with a single optional `default` block; each block should be terminated using the `break` keyword. `switch` blocks support case fall-through, so multiple cases can trigger the same block of code.

**Note:** nested `switch`-statements are not currently supported.

### Memory reading/writing
```
lwz <var>, <offset>(<base>)
sth <var>, <offset>(<base>)
```
Memory accesses are performed using a read/write mnemonic followed by a variable name, a comma, and an address construct. This expression consists of either a number or variable followed by a variable in parentheses, with the address read from/wrote to calculated as (base) + (offset).

The full list of supported mnemonics can be found in [data/ops.py](https://github.com/bgsamm/PBRScript/blob/master/data/ops.py). To learn more about these mnemonics, visit https://www.ibm.com/docs/en/aix/7.3?topic=reference-appendix-f-powerpc-instructions.
