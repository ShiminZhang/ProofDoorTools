smt_path="./ProofDoorBenchmark/smts/40/"
k_value=$(echo "$smt_path" | grep -o '[0-9]\+' | tail -n 1)
echo "k_value: $k_value"
k_value=$(echo "$smt_path" | grep -o '/[0-9]\+/' | tail -n 1)
echo "k_value: $k_value"

array_index=100
instance_index=$(($array_index / $k_value))
instance_partition_index=$(($array_index % $k_value))
echo "instance_index: $instance_index"
echo "instance_partition_index: $instance_partition_index"
