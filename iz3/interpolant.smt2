(declare-const a Int)
(declare-const b Int)
(declare-const c Int)
(declare-const d Int)
(compute-interpolant
   (and (= a b) (= a c))
   (and (= b d) (not (= c d))))