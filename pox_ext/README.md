# POX Controllers
This directory contains remote routing controllers written using the POX framework.

## Usage
1. Ensure that the directory above this directory (`pox_controller`) is in your Python path
2. Run POX with the argument `pox_controller.[controller name]` where the controller name is the name of one of the files in this directory
3. `python ~/pox/pox.py pox_controller.linear_controller`

## Controllers
### `linear_controller`
The `linear_controller` code contains a controller that is essentially a modification of the OpenFlow
tutorial included in the POX project. It will function for topologies with no cycles (single path between
any pair of nodes). This controller can be used with the `linear` Mininet topology to make sure your system
is set up correctly.

