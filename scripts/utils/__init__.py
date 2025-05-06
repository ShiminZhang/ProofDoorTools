import os
import re
import glob
import json
from tqdm import tqdm

def GetData(folder, name, use_cache=False, bit=None):
    """
    Retrieves solver data from log files or cache.
    
    Args:
        folder (str): Path to the folder containing log files
        name (str): Name of the solver
        use_cache (bool): Whether to use cached data if available
        bit (str, optional): Specific bit configuration to filter logs
        
    Returns:
        tuple: (data_for_this_solver, instance_time_map, par2, instance_mem_map)
    """
    from .utils import GetData as GetDataImpl
    return GetDataImpl(folder, name, use_cache, bit)

def compute_cnf_size_for_category(category, K, use_cache=False):
    """
    Computes CNF sizes for a specific category.
    
    Args:
        category (str): Formula category
        K (str): K value (e.g., "K1")
        use_cache (bool): Whether to use cached data if available
        
    Returns:
        dict: Dictionary mapping instance names to CNF sizes
    """
    from .process_cnf import compute_cnf_size_for_category as compute_impl
    return compute_impl(category, K, use_cache)

def compute_cnf_sizes(cnf_path, K, use_cache=False):
    """
    Computes sizes for all CNF files in a directory.
    
    Args:
        cnf_path (str): Path to the directory containing CNF files
        K (str): K value
        use_cache (bool): Whether to use cached data if available
        
    Returns:
        dict: Dictionary mapping file names to CNF sizes
    """
    from .process_cnf import compute_cnf_sizes as compute_impl
    return compute_impl(cnf_path, K, use_cache)

def compute_N_map(K, use_cache=False):
    """
    Computes a mapping of CNF files to their number of literals.
    
    Args:
        K (str): K value
        use_cache (bool): Whether to use cached data if available
        
    Returns:
        dict: Dictionary mapping file names to number of literals
    """
    from .process_cnf import compute_N_map as compute_impl
    return compute_impl(K, use_cache)

def get_category(instance_name):
    """
    Retrieves the category of an instance based on its name.
    
    Args:
        instance_name (str): Name of the instance
        
    Returns:
        str: Category of the instance
    """
    from .catagory import get_category as get_impl  
    return get_impl(instance_name)

def get_instance_list(category):
    """
    Retrieves a list of instances for a specific category.

    Args:
        category (str): Category of instances
        
    Returns:
        list: List of instance names"
    """
    from .catagory import get_instance_list as get_impl
    return get_impl(category)

def get_linear_instances():
    """
    Retrieves a list of linear instances."
    """
    from .catagory import get_linear_instances as get_impl
    return get_impl()

def get_polynomial_instances():
    """
    Retrieves a list of polynomial instances.
    """
    from .catagory import get_polynomial_instances as get_impl
    return get_impl()

def get_exponential_instances():
    """
    Retrieves a list of exponential instances.
    """
    from .catagory import get_exponential_instances as get_impl
    return get_impl()   
