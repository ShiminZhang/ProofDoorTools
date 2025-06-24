import os

# def clear_interpolant_logs():
#     os.system("rm ProofDoorBenchmark/interpolant/*.json")

# def clear_absorption_logs():
#     os.system("rm ./SlurmLogs/absorption_experiments_*")

# def clear_all_logs():
#     clear_interpolant_logs()
#     clear_absorption_logs()
def main():
    os.system("rm -rf ProofDoorBenchmark/absorption_experiments/caches/")
    # os.system("rm -r Outputs/ && mkdir Outputs/")
    # os.system("rm -r PDsizeLogs/ && mkdir PDsizeLogs/")
    # os.system("rm -r running/ && mkdir running/")
    # os.system("rm -r solve_log_dir/ && mkdir solve_log_dir/")
    # os.system("rm -r ProofDoorBenchmark/PDsizeLogs/ && mkdir ProofDoorBenchmark/PDsizeLogs/")
    # os.system("rm -r ProofDoorBenchmark/logs/ && mkdir ProofDoorBenchmark/logs/")
    # os.system("rm -r ProofDoorBenchmark/Outputs/ && mkdir ProofDoorBenchmark/Outputs/")
    # os.system("rm -r ProofDoorBenchmark/solvelogs/ && mkdir ProofDoorBenchmark/solvelogs/")
    # os.system("rm ProofDoorBenchmark/*.out")
    

if __name__ == "__main__":
    main()