#!/usr/bin/python

"""
Create a network and random_uploads on each host
to generate random TCP connections
"""

import sys

from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import lg, info
from mininet.node import Node, RemoteController, OVSSwitch
from mininet.util import waitListening

from diamond import DiamondTopoEqualWeight

def DiamondNet( edge_hosts, **kwargs ):
    "Convenience function for creating tree networks."
    topo = DiamondTopoEqualWeight( edge_hosts )
    return Mininet( topo, **kwargs )

def random_uploads( network ):
    
    network.start()
       
    for host in network.hosts:
        ip_end = host.IP()[host.IP().rfind('.')+1:]
        cmd = "python3 ~/network-optimizer/random_uploader.py 10.0.0 {} 9000 {} > ./logs/{}-log 2>&1 &".format(ip_end, len(network.hosts), str(host))
        host.cmd(cmd)
       
    CLI( network )
    
    for host in network.hosts:
        host.cmd("kill % python3")
    
    network.stop()

if __name__ == '__main__':
    hosts = 1

    if len(sys.argv) == 2:
        hosts = int(sys.argv[1])

    lg.setLogLevel( 'info')
    net = DiamondNet( 
        edge_hosts = hosts, 
        controller=lambda name: RemoteController( name, ip='127.0.0.1' ),
        switch=OVSSwitch,
        autoSetMacs=True)

    random_uploads(net)
