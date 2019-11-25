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
        log.debug("Connection {} -> {} started".format(event.src, event.dest))
        
        # Key for dict lookup
        key = tuple(sorted([event.dest, event.src]))
        
        # Check if the connection already exists
        # on one of the routes. If so, just mark it
        # as being used another time        
        if key in self.__up_connections:
            log.info("Connection {} <-> {} already being routed up".format(event.dest, event.src))
            self.__up_connections[key] += 1

            
        elif key in self.__down_connections:
            log.info("Connection {} <-> {} already being routed down".format(event.dest, event.src))
            self.__down_connections[key] += 1

             
        # Doesn't exist? If there's more connections on one side than the other
        # add it to the one side, otherwise add it up
        else:
            if len(self.__down_connections) < len(self.__up_connections):
                if core.diamond_router.add_route_down(event.src, event.dest):
                    log.info("Connection {} <-> {} routed down".format(event.src, event.dest))
                    self.__down_connections[key] = 1
            else:
                if core.diamond_router.add_route_up(event.src, event.dest):
                    log.info("Connection {} <-> {} routed up".format(event.src, event.dest))
                    self.__up_connections[key] = 1
        
        log.info("{} connections routed down, {} routed up".format(len(self.__down_connections), len(self.__up_connections)))
        
    def __connectionEnded(self, event):
        log.debug("Connection {} -> {} ended".format(event.src, event.dest))
        
        # Key for dict lookup
        key = tuple(sorted([event.dest, event.src]))
        
        # Check which way the connection went
        # and mark it one less; if it's at 0 now,
        # undo the routing     
        if key in self.__up_connections:
            self.__up_connections[key] -= 1
            if self.__up_connections[key] == 0:
                log.info("Connection {} <-> {} is unused, removing up route".format(event.dest, event.src))
                del self.__up_connections[key]
                core.diamond_router.remove_route_up(event.src, event.dest)
            else:
                log.info("Connection {} <-> {} is used {} times; staying routed up".format(event.dest, event.src, self.__up_connections[key]))   
            
        elif key in self.__down_connections:
            self.__down_connections[key] -= 1
            if self.__down_connections[key] == 0:
                log.info("Connection {} <-> {} is unused, removing down route".format(event.dest, event.src))
                del self.__down_connections[key]
                core.diamond_router.remove_route_down(event.src, event.dest)
            else:
                log.info("Connection {} <-> {} is used {} times; staying routed down".format(event.dest, event.src, self.__down_connections[key]))   

        # Rebalance; if there's > 2 difference between the sides
        while len(self.__up_connections) > len(self.__down_connections) + 1:
            key, value = self.__up_connections.popitem()
            log.info("Moving connection {} <-> {} from up to down".format(key[0], key[1]))
            core.diamond_router.remove_route_up(key[0], key[1])
            core.diamond_router.add_route_down(key[0], key[1])
            
        while len(self.__down_connections) > len(self.__up_connections) + 1:
            key, value = self.__down_connections.popitem()
            log.info("Moving connection {} <-> {} from down to up".format(key[0], key[1]))
            core.diamond_router.remove_route_down(key[0], key[1])
            core.diamond_router.add_route_up(key[0], key[1])
            
        log.info("{} connections routed down, {} routed up".format(len(self.__down_connections), len(self.__up_connections)))
        
def try_launch():
    manager = ConnectionManager()
    
    core.register("diamond_manager", manager)

def launch ():
    core.call_when_ready(try_launch, ["diamond_listener", "diamond_router"])

  
