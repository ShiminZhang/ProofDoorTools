import argparse
from utils.catagory import get_instance_list
from utils.utils import GetPDS, GetData
from utils.paths import get_cnfs_dir
from utils.draw import init_plot, draw_scaling_plot_line, finish_plot
from utils.process_cnf import compute_cnf_size_for_category, CNF
from utils.absorption_analysis import compute_wire_and_save

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, default=20)
    parser.add_argument("--pddef", type=int, default=1)
    parser.add_argument("--category", type=str, default="all")
    parser.add_argument("--PDSvsFormulaSize", action="store_true")
    parser.add_argument("--WireSizevsFormulaSize", action="store_true")
    return parser.parse_args()

def PDSvsFormulaSize(args):
    interested_instances = get_instance_list(args.category)[:10]
    # interested_instances = ["139442p0", "139444p0", "139452p0", "139462p0", "139464p0"]
    # for each K, get the average among all the instances
    avg_pds_map = {}
    avg_formula_size_map = {}
    for K in range(1,9,1):
        pds_map = GetPDS(K,args.pddef,interested_instances)
        formula_size_map = compute_cnf_size_for_category(args.category,K,use_cache=False,interested_instances=interested_instances)
        # print(pds_map)
        skip_keys = ["139443p5", "139444p22"]
        for key in pds_map:
            # assert(pds_map[key] > 0)
            if pds_map[key] <= 0:
                print(f"Warning: pds_map[{key}] <= 0, instance: {key.split('.')[0]}")
                skip_keys.append(key)
                continue
            if key.split(".")[0] not in interested_instances:
                print(f"key {key} not in interested_instances")
        for key in skip_keys:
            if key in formula_size_map:
                del formula_size_map[key]
            if key in pds_map:
                del pds_map[key]
        average_pds = sum(pds_map.values()) / len(pds_map)
        average_formula_size = sum(formula_size_map.values()) / len(formula_size_map)
        avg_pds_map[K] = average_pds
        avg_formula_size_map[K] = average_formula_size
        # print(pds_map.keys())
        print(f"K={K}, average PDS={average_pds}, average formula size={average_formula_size}, length={len(pds_map)}")
    #draw the plot
    init_plot("Average interpolant size","Average Formula Size",f"scaling plot: interpolant size vs formula size with {args.category} instances")
    draw_scaling_plot_line(list(avg_pds_map.values()),list(avg_formula_size_map.values()),"PDS-FS")
    # draw_scaling_plot_line(list(avg_formula_size_map.keys()),list(avg_formula_size_map.values()),"Formula Size")
    finish_plot(f"PDSvsFormulaSize_{args.category}.png")


def WireSizevsFormulaSize(args):
    interested_instances = get_instance_list(args.category)[:10]
    # interested_instances = get_interested_instances(args.category)
    # for each K, get the average among all the instances
    avg_wire_size_map = {}
    avg_formula_size_map = {}    
    for K in range(1,21,1):
        sum_wire_size = 0
        for instance in interested_instances:
            local_wire_size_map = compute_wire_and_save(CNF.from_file(f"ProofDoorBenchmark/cnfs/{K}/{instance}.{K}.cnf"))
            local_avg_wire_size = sum(local_wire_size_map.values()) / len(local_wire_size_map)
            sum_wire_size += local_avg_wire_size
        avg_wire_size = sum_wire_size / len(interested_instances)
        avg_wire_size_map[K] = avg_wire_size
        formula_size_map = compute_cnf_size_for_category(args.category,K)
        avg_formula_size = sum(formula_size_map.values()) / len(formula_size_map)
        avg_formula_size_map[K] = avg_formula_size
        print(f"K={K}, average wire size={avg_wire_size}, average formula size={avg_formula_size}, length={len(interested_instances)}")
        
    init_plot("Wire Size","Formula Size","Wire Size vs Formula Size")
    draw_scaling_plot_line(list(avg_wire_size_map.values()),list(avg_formula_size_map.values()),"Wire Size - Formula Size")
    finish_plot(f"WireSizevsFormulaSize_{args.category}.png")

def PDSvsSolvingTime(args):
    interested_instances = get_interested_instances(args.category)
    # for each K, get the average among all the instances
    avg_pds_map = {}
    avg_solving_time_map = {}
    for K in range(1,args.K+1,1):
        pds_map = GetPDS(K,args.pddef,interested_instances)

        average_interpolant_size = sum(pds_map.values()) / len(pds_map)
        average_pds = average_interpolant_size * K
        avg_pds_map[K] = average_pds
        print(f"K={K}, average PDS={average_pds}, length={len(pds_map)}")

        data_for_this_solver,solving_time_map,par2,instance_mem_map = GetData(f"logs/K_{K}/",args.pddef,interested_instances)

        print(f"K={K}, par2={par2}, length={len(solving_time_map)}")
        average_solving_time = par2
        avg_solving_time_map[K] = average_solving_time

    #draw the plot
    init_plot("PDS","Solving Time","PDS vs Solving Time")
    draw_scaling_plot_line(list(avg_pds_map.keys()),list(avg_pds_map.values()),"PDS")
    draw_scaling_plot_line(list(avg_solving_time_map.keys()),list(avg_solving_time_map.values()),"Solving Time")
    finish_plot("plots/PDSvsSolvingTime.png")


    pds_map = GetPDS(args.K,args.pddef,interested_instances)


    pass    

def WireSizevsSolvingTime(args):
    pass

def main():
    args = get_args()
    print(args)
    if args.PDSvsFormulaSize:
        PDSvsFormulaSize(args)
        return
    if args.WireSizevsFormulaSize:
        WireSizevsFormulaSize(args)
        return
    if args.PDSvsSolvingTime:
        PDSvsSolvingTime(args)
        return
    if args.WireSizevsSolvingTime:
        WireSizevsSolvingTime(args)
if __name__ == "__main__":
    main()