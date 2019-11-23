
"""
This component is for use with the diamond topology.

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
     
There are expected to be the same number of hosts attached to
switches 1 and 4 

Additionally it assumes that the dpid of switch 1 is 1, the dpid of
switch 2 is 2, and so forth. Finally, it takes as a command line argument
the number N of how many switches are on either side of the diamond, and assumes
that the hosts on the left use ip address 10.0.0.1-10.0.0.n and that the hosts 
on the right are 10.0.0.n+1 - 10.0.0.2n

This controller makes the final assumptions that all traffic between the hosts will
use a TCP connection, and therefore it is possible to use SYN and FIN messages
to know when connections are going up or down, and that the connection is fairly one-sided
as in the case of a file download.
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of

log = core.getLogger("diamond-controller")

class SmartSwitchController (object):
    """
    Controller for one of the two switches on the side
    of the diamond.
    
    On startup, the controller will set the following rules
    * Ports 1 and 2 will be marked no-flood
    * Any message received on port > 2 will be forwarded to this controller,
        flooded to all ports > 2, and forwarded to port 1
    * Any message received on port 1 or port 2, which has a destination
        in one of the directly attached hosts will be flooded to all ports
        other than 1 and 2
    * Any message received on port 1 or port 2 which has a destination
        in a host that is not directly attached will be dropped
    
    This initial configuration should support general communication
    around the diamond. After startup, the following modifications
    will be automatically made
    
    When a message is received on port > 2, the mac address of the sender
    will be recorded and two new flow rules will be added with higher priority
    than the default rules.
    * Messages with that mac will be forwarded to that port
    * Messages from that port will be forwarded to port 1
    
    Finally, during runtime, this controller can be commanded to set the route
    for a specific IP address pair to be port 1 or 2. If exactly 1 of the IP addresses
    is a locally connected host, then at that point, two things will happen
    * Any flow for that IP address pair will be removed
    * A new flow will be installed to route from the locally attached IP to the target port
    
    Note, this last control option will fail if the port number for the locally attached IP
    is unknown. To resolve this, ensure that both of hosts using the IP addresses have sent
    at least one IP message before calling this. This can easily be done by
    * Having every host on the network ping every other host
    * Waiting for a TCP connection to be established before setting this route
    """
    
    PRIORITY_FLOOD_FORWARD_ALWAYS = of.OFP_DEFAULT_PRIORITY + 1
    PRIORITY_FLOOD_IF_PORT = PRIORITY_FLOOD_FORWARD_ALWAYS + 1
    
    def __no_flood_mod(self, port):
        """
        Creates a port mod message to disable flooding to a port
        """
        msg = of.ofp_port_mod()
        msg.port_no = port
        msg.hw_addr = self.__connection.ports[port].hw_addr
        msg.config = of.OFPPC_NO_FLOOD
        msg.mask = of.OFPPC_NO_FLOOD
        msg.advertise = 0
        
        return msg
        
    def __flood_and_forward_always_mod(self):
        """
        Creates a flow mod to flood
        flood any messages received,
        forward to port 1, and forward to controller
        """
        msg = of.ofp_flow_mod()
        msg.priority = self.PRIORITY_FLOOD_FORWARD_ALWAYS
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
        msg.actions.append(of.ofp_action_output(port = 1))
        msg.actions.append(of.ofp_action_output(port = of.OFPP_CONTROLLER))
        
        return msg;
        
    def __flood_if_port_mod(self, port_num):
        """
        Creates a flow mod to flood
        flood any messages received
        on a specific port
        """
        msg = of.ofp_flow_mod()
        msg.priority = self.PRIORITY_FLOOD_IF_PORT
        msg.match.in_port = port_num
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
        return msg;
        
    def __set_initial_config(self):
        # Ports 1 and 2 will be marked no-flood
        self.__connection.send(self.__no_flood_mod(1))
        self.__connection.send(self.__no_flood_mod(2))
        
        # Any message received will be forwarded to this controller,
        # flooded, and forwarded to port 1.
        # Since ports 1 and 2 are no-flood, it will only flood
        # to the ports > 2
        self.__connection.send(self.__flood_and_forward_always_mod())
        
        # Any message received on port 1 or port 2 will be flooded to all ports
        # other than 1 and 2; this will preempt the mod above by priority
        # so messages from ports 1 and 2 will not get forwarded to port 1
        # or to this controller
        self.__connection.send(self.__flood_if_port_mod(1))
        self.__connection.send(self.__flood_if_port_mod(2))
    
    def __init__(self, connection):
        log.info("Smart switch {} connected".format(connection.dpid))
        
        self.__connection = connection
        self.__dpid = connection.dpid
        
        self.__connection.addListenerByName("PacketIn", self.__packetIn)
        self.__connection.addListenerByName("PortStatus", self.__portStatus)
        
        self.__ports = {}

        self.__set_initial_config()
            
    def __packetIn(self, event):
        packet_type = event.parsed # This is the parsed packet data.
        if not packet_type.parsed:
          log.warning("Ignoring incomplete packet")
          return

        packet_in = event.ofp # The actual ofp_packet_in message.
        log.info("Switch {} got packet on port {}".format(self.__dpid, event.port))
        
    def __portStatus(self, event):
        if event.added:
            log.info("Switch {} added port {}".format(self.__dpid, event.port))
        elif event.deleted:
            log.info("Switch {} removed port {}".format(self.__dpid, event.port))
    
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

class EqualDiamondController (object):
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

def launch ():
    controller = EqualDiamondController()
    core.register(controller, "diamond_controller")
  
