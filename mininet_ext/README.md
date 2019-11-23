# Mininet Extensions
This directory contains code to extend mininet and produce new topologies.

## Usage
1. Run Mininet from this directory, using the `--custom` command line argument to add one of the extensions and the `--topo` argument to pick the topology.
2. `sudo mn --custom [filename.py] --topo [topology name]`
3. It may be desirable to add some extra arguments like `--switch ovsk --mac --controller remote`

## Extensions
### `linear`
The `linear` extension adds a topology that looks like a line of M switches with N hosts connected to each.
This is similar to the built-in mininet `linear` topology, but it allows you to specify the number of hosts per switch.
This topology can be used with the POX `linear_controller` to make sure that your system is set up correctly.

```
--topo linear,3,3

        n n n
n \      \|/      / n
n - s --- s --- s - n
n /               \ n
```

### 'diamond`