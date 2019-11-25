# Network Optimizer

Experimental project to demonstrate the use of the OpenFlow protocol to
configure a network.

Submitted Fall 2019 as a requirement of the Networking
course at SDSM&T

## Problem Statement

You have a diamond-shaped network, as shown below. 
Write an OpenFlow controller to...

A. Facilitate general routing across the diamond

B. Listen to an extra data channel from applications
on the host systems, and use the information gathered
to balance the network


    h \   / s \   / h
    h - s       s - h
    h /   \ s /   \ h


In this network, you have 4 switches connected in a diamond pattern.
To opposing switches on the diamond have extra hosts connected to them, and
these hosts will attempt to communicate with each other.

## What's in this solution

This solution was written using to important libraries:

1. Mininet is used to simulate the network
2. POX is used to manage the controller and OpenFlow communication.

This project contains a number of distinct pieces, there's
4 main 'chunks' of code

1. sockets_lib - A small library for abstracting socket communication.
I had previously written it and wanted to use it for more things. It is used 
on the client side of the back-channel communcation with the controller
2. random_uploader.py - A bot script to simulate communcation between the hosts.
It runs a TCP Server, and then periodically attempts to connect to another host
and send a bunch of information to its TCP server. It may attempt to connect to
itself. Additionally, it sends UDP messages to the address given as the controller
to notify it when it starts/stops uploads.
3. mininet_ext - Code for creating and running the diamond topology in Mininet
    * diamond.py - Contains a mininet custom plugin that adds the diamond topology
    * random_uploads_diamond.py - Is a script to start the Mininet, open a NAT connection to the host
    system, and start the upload bot on each Mininet host.
4. pox_ext/diamond - Modules to run in the POX framework to control this topology
    * router.py - General router module to ensure packets can flow through the topology
    * connection_listener.py - UDP listener to receive messages from the upload bots and generate UploadStarted/UploadStopped events
    * connection_manager.py - Balancer to route TCP streams through either the 'top' or 'bottom' of the diamond so that there
    is always as close as possible to an equal number on each side. This module requires the previous two to function.
    
### Constraints

To simplify the problem, a few constraints have been placed on how the solution functions.

1. The POX controller is started before the network is brought online
2. The network does not change after it is started
3. The port numbers and DPIDs of the switches are always the same, as described in the POX code for the router

## Usage

* Ensure that both Mininet and POX are installed. Installing Mininet will usually install POX. An easy solution is to grab the Mininet VM image and run inside of it.

* Ensure Python3 is installed

* To run the POX controller, execute `python2 ~/pox/pox.py pox_ext.diamond.router pox_ext.diamond.connection_listener --address={ip-address} [--port={port-num}] pox_ext.diamond.connection_manager` from the root of this repo (assuming POX is installed in your home directory). Be sure to have the listener use an IP address that the host system can reach (using the address of your `eth0` device works
well). This port will default to 6634. If you would like to just use default
non-connection-oriented routing rules, use `python2 ~/pox/pox.py pox_ext.diamond.router` to start only the router. You may want
to add `log.level --DEBUG` or `log.level --INFO` to get extra output from the tool. Most messages from this project are at the INFO level.

* To start the network, execute `./mininet_ext/random_uploads_diamond.py {ip-address} [n] [port]` from the root of this repo. Be sure to use the same IP address and port as you did when starting the POX connection listener. `n` is the number of hosts that should be attached
on the two sides of the diamond.

At this point, you should start seeing output from the POX controller indicating when it connects to switches, learns MAC addresses, and
starts routing connections up or down on the diamond. Mininet will create a `logs` directory where you can see the output from all of the
upload bots.
