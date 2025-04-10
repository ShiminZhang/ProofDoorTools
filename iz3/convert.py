from z3 import *

s = Solver()
# s.from_file("test.cnf")
s.from_file("test2.smt2")
print(s)
print(s.check())
print(s.model())