from utils.process_cnf import CNF

def main():
    cnf = CNF.from_file("ProofDoorBenchmark/cnfs/10/beembrptwo6b1.10.cnf")
    print(cnf.get_N())
    print(cnf.get_L())
    print(cnf.get_clauses())
    print(cnf.get_iter_map())
    print(cnf.get_literals())
    print(cnf.get_literal_map())
    print(cnf.get_literal_set())

if __name__ == "__main__":
    main()