(declare-const a Int)
(declare-const b Int)
(declare-const c Int)
(compute-interpolant
   (or (= a 1) (= c 1))
   (and (and (= b 1) (= c 0) (= a 0))))