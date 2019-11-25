"""
This component is a connection manager for a diamond network topology.
It takes information from the hosts about what connections 
they are making and tries to route traffic in a balanced fashion

It assumes that there is a network with the following setup

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
                   
s2 and s3 are two switches which are connected to with ports
1 and 2. Switches 1 and 4 connect to switch 2 on port 1 
and switch 3 on port 2, and an arbitrary number of other hosts
on the rest of their ports.

It is expected that the network configuration will not change after startup

This component requires two other components to function. It uses a component
registered as 'diamond_listener' to know when connections start and end, and 
it uses a componenet registered as 'diamond_router' to enact changes on the
system
"""
from pox.core import core
from pox.lib.recoco import Timer

import time

log = core.getLogger("diamond.connection-manager")

class ConnectionManager(object):
    def __init__(self):
        # Mapping from source to destination
        self.__up_connections = {}
        self.__down_connections = {}
        
        log.info("Starting unweighted diamond connection manager")

        core.diamond_listener.addListenerByName("UploadStarted", self.__connectionStarted)
        core.diamond_listener.addListenerByName("UploadEnded", self.__connectionEnded)

    def __connectionStarted(self, event):
        log.info("Connection {} -> {} started".format(event.src, event.dest))
        core.diamond_router.add_route_up(event.src, event.dest)
        
    def __connectionEnded(self, event):
        log.info("Connection {} -> {} ended".format(event.src, event.dest))
        core.diamond_router.remove_route_up(event.src, event.dest)
        
def try_launch():
    manager = ConnectionManager()
    
    core.register("diamond_manager", manager)

def launch ():
    core.call_when_ready(try_launch, ["diamond_listener", "diamond_router"])

  
