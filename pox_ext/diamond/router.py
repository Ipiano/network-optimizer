
"""
This component is a router for a diamond network topology.
It ensures that all hosts on the network will be able to send
data to all other hosts.

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

Additionally it assumes that the dpid of switch 1 is 1, the dpid of
switch 2 is 2, and so forth. 
"""

from pox.core import core
from pox.lib.addresses import EthAddr, IPAddr
import pox.openflow.libopenflow_01 as of

from .flow_table_priorities import *

log = core.getLogger("diamond.router")

class MissingPortError(Exception):
    def __init__(self, port):
        self.port = port

class SmartSwitchController (object):
    """
    Controller for one of the two switches on the sides
    of the diamond.
    
    On startup, the controller will set the following rules
    1. Ports 1 and 2 will be marked no-flood
    2. Any message received on port > 2 will be forwarded to this controller,
        flooded to all ports > 2, and forwarded to port 1
    3. Any message received on port 1 or port 2 will be flooded to all ports
        other than 1 and 2, and also forwarded to this controller
        
    This initial configuration supports general communication
    around the diamond. After startup, the following modifications
    will be automatically made
    
    When a message is received, the mac (and, if it's not on port 1 or 2 IP) address of the sender
    will be recorded and new flow rules will be added with higher priority
    than the default rules.
    4. Messages for that mac will be forwarded to that port (if the port is 2, 1 will be used)
    5a. Messages from that mac will be forwarded to port 1 and flooded (if it is not on port 1 or 2)
    5b. Messages from that mac will be flooded to all local ports (if it is on port 1 or 2)
    
    Note, for this to work, rule 5 must be lower priority than rule 4
    """
    
    def __no_flood_mod(self, port):
        """
        Creates a port mod message to disable flooding to a port
        """
        msg = of.ofp_port_mod()
        msg.port_no = port
        msg.config = of.OFPPC_NO_FLOOD
        msg.mask = of.OFPPC_NO_FLOOD
        msg.advertise = 0
        
        try:
            msg.hw_addr = self.__connection.ports[port].hw_addr
        except IndexError as ex:
            raise MissingPortError(port)
        
        return msg
        
    def __flood_and_forward_local_mod(self):
        """
        Creates a flow mod to flood
        flood any messages received,
        forward to port 1, and forward to controller
        """
        msg = of.ofp_flow_mod()
        msg.priority = PRIORITY_FLOOD_FORWARD_ALWAYS
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
        msg.actions.append(of.ofp_action_output(port = 1))
        msg.actions.append(of.ofp_action_output(port = of.OFPP_CONTROLLER))
        
        return msg;
       
    def __flood_and_forward_other_mod(self, port):
        """
        Creates a flow mod to flood
        flood any messages received,
        and forward to controller, from a specific port
        """
        msg = of.ofp_flow_mod()
        msg.priority = PRIORITY_FLOOD_IF_PORT
        msg.match.in_port = port
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
        msg.actions.append(of.ofp_action_output(port = of.OFPP_CONTROLLER))
        
        return msg;
        
    def __send_for_mac_to_port_mod(self, mac, port):
        """
        Creates a flow mod to send messages for a specific
        mac address to a specific port #
        """
        msg = of.ofp_flow_mod()
        msg.priority = PRIORITY_SEND_TO_MAC
        msg.match.dl_dst = mac
        msg.match.port = None
        msg.actions.append(of.ofp_action_output(port = port))
        
        return msg;
        
    def __flood_and_forward_from_mac_mod(self, mac):
        """
        Creates a flow mod to send messages from a specific
        mac address to port 1 and flood them
        """
        msg = of.ofp_flow_mod()
        msg.priority = PRIORITY_SEND_FROM_MAC
        msg.match.dl_src = mac
        msg.match.port = None
        msg.actions.append(of.ofp_action_output(port = 1))
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
        
        return msg;

    def __flood_from_mac_mod(self, mac):
        """
        Creates a flow mod to flood messages from a specific
        mac address
        """
        msg = of.ofp_flow_mod()
        msg.priority = PRIORITY_SEND_FROM_MAC
        msg.match.dl_src = mac
        msg.match.port = None
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
        
        return msg;
              
    def __ip_route_add_mod(self, local_ip, other_ip, port):
        """
        Produces a flow mod to send messages from the given
        ip address out the target port.
        """
        msg = of.ofp_flow_mod()
        msg.priority = PRIORITY_ROUTE_CONNECTION
        msg.match.nw_src = (IPAddr(local_ip), 32)
        msg.match.nw_dst = (IPAddr(other_ip), 32)
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port = port))
        
        return msg
        
    def __ip_route_delete_mod(self, local_ip, other_ip, port):
        """
        Produces a flow mod to remove a flow mod
        to send messages from the given
        ip address out the target port.
        """
        msg = self.__ip_route_add_mod(local_ip, other_ip, port)
        msg.command = of.OFPFC_DELETE
        msg.actions = []
        msg.out_port = port
        
        return msg
      
    def __clear_table_mod(self):
        """
        Produces a flow mod to clear the table
        """
        msg = of.ofp_flow_mod()
        msg.command = of.OFPFC_DELETE
        
        return msg
        
    def __set_default_route(self):
        # 0. Clear the table
        self.__connection.send(self.__clear_table_mod())
        
        # 1. Ports 1 and 2 will be marked no-flood
        self.__connection.send(self.__no_flood_mod(1))
        self.__connection.send(self.__no_flood_mod(2))
        
        # 2. Any message received will be forwarded to this controller,
        # flooded, and forwarded to port 1.
        # Since ports 1 and 2 are no-flood, it will only flood
        # to the ports > 2
        self.__connection.send(self.__flood_and_forward_local_mod())
        
        # 3. Any message received on port 1 or port 2 will be flooded to all ports
        # other than 1 and 2, and also forwarded to this controller
        self.__connection.send(self.__flood_and_forward_other_mod(1))        
        self.__connection.send(self.__flood_and_forward_other_mod(2))
        
    def __learn_port_route(self, port, mac):
        """
        Learns that a specific mac address is attached
        to a specific port and reconfigures the switch
        according to rules 5 and 6
        """
        # Future Improvements to support dynamic hosts: 
        #
        # Track port -> mac also. If port assigned to different
        # mac, then undo that assignment so that if that device is plugged
        # in elsewhere, its messages are forwarded to controller by rule 2
        #
        # Listen to portadded/portremoved messages to do some of this configuration
        #
        # Put a fairly short timeout on rules 4 and 5 so that if the device is unplugged
        # its flow rule will be un-learned
        
        if mac in self.__mac_to_port:
            self.log.debug("Duplicate port/mac mapping: {} -> {}".format(port, mac))
            return
        
        # Outgoing messages to the diamond always default to port 1
        port = 1 if port == 2 else port
        
        self.log.info("Mapping mac {} to port {}".format(mac, port))
        self.__mac_to_port[mac] = port
        
        # 4. Messages for that mac will be forwarded to that port
        self.__connection.send(self.__send_for_mac_to_port_mod(mac, port))
        
        # 5. Messages from that mac will be flooded and forwarded to port 1
        # or just flooded
        if port == 1:
            self.__connection.send(self.__flood_from_mac_mod(mac))
        else:
            self.__connection.send(self.__flood_and_forward_from_mac_mod(mac))
        
    def __try_set_default_route(self):
        if self.__default_route_is_setup:
            return
    
        try:
            self.__set_default_route()
            self.log.info("Setup default routes")
            self.__default_route_is_setup = True
        except MissingPortError as ex:
            self.log.warning("Unable to set default route; missing port {}".format(ex.port))
   
    
    def __init__(self, connection):
        self.__connection = connection
        self.__dpid = connection.dpid
        self.__default_route_is_setup = False
        
        self.log = log.getChild("switch-{}".format(self.__dpid))
        self.log.info("Smart switch {} connected".format(self.__dpid))
        
        self.__connection.addListenerByName("PacketIn", self.__packetIn)
        self.__connection.addListenerByName("PortStatus", self.__portStatus)
        
        self.__mac_to_port = {}
        self.__learned_ips = set()

        self.log.info("Attempting to set up default routes...")
        self.__try_set_default_route()
            
    def __packetIn(self, event):
        packet_type = event.parsed # This is the parsed packet data.
        if not packet_type.parsed:
          self.log.warning("Ignoring incomplete packet")
          return

        packet_in = event.ofp # The actual ofp_packet_in message.
        self.log.debug("Got packet on port {}".format(event.port))
        
        eth = packet_type.find("ethernet")
        ip = packet_type.find("ipv4")
        if ip and eth:
            self.__learn_port_route(event.port, eth.src)
            
            # Only track IP addresses of hosts connected
            # directly
            if event.port > 2:
                self.__learned_ips.add(ip.srcip)
        
    def __portStatus(self, event):
        self.log.info("Ports changed!")

        self.__try_set_default_route()
        
    def has_learned(self, ip):
        return IPAddr(ip) in self.__learned_ips
        
    def __add_route(self, local_ip, other_ip, port):
        self.log.debug("Adding rule for {} -> {} out port {}".format(local_ip, other_ip, port))
        self.__connection.send(self.__ip_route_add_mod(local_ip, other_ip, port))
        
    def __remove_route(self, local_ip, other_ip, port):
        self.log.debug("Removing rule for {} -> {} out port {}".format(local_ip, other_ip, port))
        self.__connection.send(self.__ip_route_delete_mod(local_ip, other_ip, port))
        
    def add_route(self, src_ip, dest_ip, port):
        if self.has_learned(src_ip):
            assert(not self.has_learned(dest_ip))
            self.__add_route(src_ip, dest_ip, port)
        else:
            assert(self.has_learned(dest_ip))
            self.__add_route(dest_ip, src_ip, port)
        
    def remove_route(self, src_ip, dest_ip, port):
        if self.has_learned(src_ip):
            assert(not self.has_learned(dest_ip))
            self.__remove_route(src_ip, dest_ip, port)
        else:
            assert(self.has_learned(dest_ip))
            self.__remove_route(dest_ip, src_ip, port)
        
class DumbSwitchController (object):
    """
    Switch controller for switches 2 and 3.
    Will configure its switch to forward all information from port 1
    to port 2 and from port 2 to port 1
    """
    def __dumb_flow_mod(self, in_port, out_port):
        """
        Produces a dumb flow mod that just forwards from one
        port to another
        """
        msg = of.ofp_flow_mod()
        msg.match.in_port = in_port
        msg.actions.append(of.ofp_action_output(port = out_port))
        return msg
        

    def __init__(self, connection):
        log.info("Dumb switch {} connected; sending fowarding rules".format(connection.dpid))
        connection.send(self.__dumb_flow_mod(1, 2))
        connection.send(self.__dumb_flow_mod(2, 1))

class EqualDiamondRouter (object):
    """
    A single controller should be created on startup,
    and then given access to all connections found.
    
    Once the four expected connections have been added,
    it will begin operation.
    """
    
    def __init__ (self):
        self.__switch_1 = None
        self.__switch_2 = None
        self.__switch_3 = None
        self.__switch_4 = None
        
        log.info("Starting unweighted diamond controller")
        
        core.openflow.addListenerByName("ConnectionUp", self.__new_connection)
        
    def __new_connection(self, event):
        self.__add(event.connection)

    def __add(self, connection):
        # The two dumb switches should just take all data in one side
        # and forward it to the other. This assumes that the switch
        # uses ports 1 and 2
        if connection.dpid == 2:
            self.__switch_2 = DumbSwitchController(connection)
        elif connection.dpid == 3:
            self.__switch_3 = DumbSwitchController(connection)
            
        # When switches 1 and 4 come online, set up a smart controller
        # to work with them
        elif connection.dpid == 1:
            self.__switch_1 = SmartSwitchController(connection)
        elif connection.dpid == 4:
            self.__switch_4 = SmartSwitchController(connection)
            
        else:
            log.info("Unknown switch {} ignored".format(connection.dpid))

    """
    add/remove route functions are used
    to route messages between two sides of the diamond
    either through the top switch or the bottom. For this to
    work, there must have been at least one message sent from 
    both addresses so that their locations are known. If 
    this has not happened, the request is ignored.
    """
    
    def __route_should_be_established(self, src_ip, dest_ip):
        """
        Checks if a route should be established; this requires
        that both of the IP addresses are known by at least one of
        [switch 1, switch 4] and that they are not both known by the same
        switch (that would be a useless rule to add)
        """
        if not self.__switch_1 or not self.__switch_4:
            log.warning("Cannot establish route: Switches not online")
            return False
        
        src_learned_by = 0
        if self.__switch_1.has_learned(src_ip):
            src_learned_by = 1
        elif self.__switch_4.has_learned(src_ip):
            src_learned_by = 4
       
        dest_learned_by = 0
        if self.__switch_1.has_learned(dest_ip):
            dest_learned_by = 1
        elif self.__switch_4.has_learned(dest_ip):
            dest_learned_by = 4
       
        if not src_learned_by or not dest_learned_by:
            log.warning("Cannot establish route: {} or {} not known".format(src_ip, dest_ip))
            return False
              
        if src_learned_by == dest_learned_by:
            log.info("Not going to establish route: {} and {} are attached to the same switch".format(src_ip, dest_ip))
            return False
            
        return True
    
    def add_route_up(self, src_ip, dest_ip):
        if self.__route_should_be_established(src_ip, dest_ip):
            self.__switch_1.add_route(src_ip, dest_ip, 1)
            self.__switch_4.add_route(src_ip, dest_ip, 2)
            return True
        return False
            
    def add_route_down(self, src_ip, dest_ip):
        if self.__route_should_be_established(src_ip, dest_ip):
            self.__switch_1.add_route(src_ip, dest_ip, 2)
            self.__switch_4.add_route(src_ip, dest_ip, 1)
            return True
        return False
        
    def remove_route_up(self, src_ip, dest_ip):
        if self.__route_should_be_established(src_ip, dest_ip):
            self.__switch_1.remove_route(src_ip, dest_ip, 1)
            self.__switch_4.remove_route(src_ip, dest_ip, 2)
        
    def remove_route_down(self, src_ip, dest_ip):
        if self.__route_should_be_established(src_ip, dest_ip):
            self.__switch_1.remove_route(src_ip, dest_ip, 2)
            self.__switch_4.remove_route(src_ip, dest_ip, 1)

def launch ():
    controller = EqualDiamondRouter()
    core.register("diamond_router", controller)
  
