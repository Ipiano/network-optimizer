#!/usr/bin/python                                                                            
                                                                                             
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import OVSSwitch, Controller, RemoteController

import time

class LinearTopoEqualWeight(Topo):
    """
    Linear topology connecting 3 nodes
    on one side with 3 nodes on the other such
    that there are two paths between the sides

    n \         / n
    n - s --- s - n
    n /         \ n
    """
    def build(self, m=2, n=3):
        h = 1
        s = 1
        previous = None
        for i in range(m):
            switch = self.addSwitch('s{}'.format(s))
            s=s+1
            
            for j in range(n):
                host = self.addHost('h{}'.format(h))
                h=h+1

                self.addLink(host, switch)

            if previous:
                self.addLink(switch, previous)
            previous = switch

topos = {'linear' : LinearTopoEqualWeight}