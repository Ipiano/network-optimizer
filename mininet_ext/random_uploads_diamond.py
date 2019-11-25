#!/usr/bin/python2

"""
Create a network and random_uploads on each host
to generate random TCP connections
"""

import sys
import os, errno


from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import lg, info
from mininet.node import Node, RemoteController, OVSSwitch
from mininet.util import waitListening
from mininet.link import Intf

from diamond import DiamondTopoEqualWeight

def DiamondNet( edge_hosts, **kwargs ):
    "Convenience function for creating tree networks."
    topo = DiamondTopoEqualWeight( edge_hosts )
    return Mininet( topo, **kwargs )

def random_uploads( network, address, port ): 
    
    # Adds a NAT adapter to switch 1
    # at ip address 10.0.0.2n+1
    network.addNAT().configDefault()
       
    network.start()
       
    for host in network.hosts[:-1]:
        ip_end = host.IP()[host.IP().rfind('.')+1:]
        cmd = "python3 ~/network-optimizer/random_uploader.py {} {} 10.0.0 {} 9000 {} > ./logs/{}-log 2>&1 &".format(address, port, ip_end, len(network.hosts)-1, str(host))
        host.cmd(cmd)

    CLI( network )
    
    for host in network.hosts[:-1]:
        host.cmd("kill % python3")
    
    network.stop()

if __name__ == '__main__': 
    if len(sys.argv) < 2:
        print("Usage: {} ip-address [port] [n]".format(sys.argv[0]))
        sys.exit(1)
        
    try:
        os.mkdir("logs")
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
           
    hosts = 1  
    address = sys.argv[1]
    port = 6634
        
    if len(sys.argv) > 2:
        hosts = int(sys.argv[2])
    
    if len(sys.argv) > 3:
        port = int(sys.argv[3])
        
    lg.setLogLevel( 'info')
    net = DiamondNet( 
        edge_hosts = hosts, 
        controller=lambda name: RemoteController( name, ip='127.0.0.1' ),
        switch=OVSSwitch,
        autoSetMacs=True)

    random_uploads(net, address, port)
