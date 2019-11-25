from pox.core import core
from pox.lib.recoco import Timer
from pox.lib.revent import Event, EventMixin

import json

from SocketServer import UDPServer, BaseRequestHandler

log = core.getLogger("diamond.listener")

class TCPConnectionEvent(Event):
    def __init__(self, source, dest):
        self.__source = source
        self.__dest = dest
        
    @property
    def src(self):
        return self.__source
        
    @property
    def dest(self):
        return self.__dest
        
class UploadStarted(TCPConnectionEvent):
    pass
    
class UploadEnded(TCPConnectionEvent):
    pass

class ConnectionHandler(BaseRequestHandler, object):
    def handle(self):
        data = self.request[0]
        
        self.server.handle_message(json.loads(data))
        
class ConnectionListener(UDPServer, EventMixin, object):
    _eventMixin_events = set([
        UploadStarted,
        UploadEnded
      ])
      
    def __init__(self):
        UDPServer.__init__(self, ("192.168.44.42", 6634), ConnectionHandler, bind_and_activate=False)
        self.allow_reuse_address = True
        self.timeout = 0.1
        self.server_bind()
        self.server_activate()
        
        self.__connections = []
        self.__poll_timer = Timer(timeToWake=0.5, callback=self.__poll, 
                                  recurring=True, started=True, selfStoppable=False)

    def __poll(self):
        self.handle_request()
        
    def handle_message(self, msg):
        # Future Improvement: Add a timeout for these
        # messages so that if a host goes down, it will
        # eventually be considered as a closed connection
        
        # Even better improvement: Find a way to use OpenFlow
        # to efficiently snoop for SYN and FIN messages instead
        # of having to bind to a UDP port
        
        log.debug("Got new message: {}".format(msg))
        
        try:
            if msg["state"] == "open":
                self.raiseEvent(UploadStarted, msg["src"], msg["dest"])
            elif msg["state"] == "close":
                self.raiseEvent(UploadEnded, msg["src"], msg["dest"])
        except KeyError:
            log.warning("Unexpected message: {}".format(msg))
                
def launch ():
    listener = ConnectionListener()
    core.register("diamond_listener", listener)
  
