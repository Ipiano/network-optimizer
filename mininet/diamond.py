#!/usr/bin/python                                                                            
                                                                                             
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import OVSSwitch, Controller, RemoteController

class DiamondTopoEqualWeight(Topo):
    """
    Diamond topology connecting n nodes
    on one side with n nodes on the other such
    that there are two paths between the sides
    
                         --------
                         |      |
                         |      |
                         |  s2  |
          --------       |      |       --------
    h === |      p1 === p1      p2 === p2      | === h
    h === |      |       --------       |      | === h
    h === |  s1  |                      |  s4  | === h
    h === |      |       --------       |      | === h
    h === |      p2 === p1      p2 === p1      | === h
          --------       |      |       --------
                         |  s3  |
                         |      |
                         |      | 
                         --------
                       
    """
    def build(self, leaves):
        switch1 = self.addSwitch('s1')
        switch2 = self.addSwitch('s2')
        switch3 = self.addSwitch('s3')
        switch4 = self.addSwitch('s4')

        self.addLink(switch1, switch2)
        self.addLink(switch1, switch3)

        self.addLink(switch4, switch3)
        self.addLink(switch4, switch2)

        for h in range(leaves):
            host = self.addHost('h%s' % (h + 1))
            self.addLink(host, switch1)

        for h in range(leaves):
            host = self.addHost('h%s' % (h + leaves + 1))
            self.addLink(host, switch4)

topos = {'diamond-equal' : DiamondTopoEqualWeight}
