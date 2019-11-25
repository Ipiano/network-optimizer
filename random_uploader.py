from sockets_lib.tcp_connection import TCPClientConnection, TCPServerConnection, TCPServer
from sockets_lib.udp_connection import UDPPublisher
from sockets_lib.connection import ConnectionPoller, ConnectionPollerThread, ConnectionIsClosedError

from threading import Thread
from functools import partial
from itertools import zip_longest

import time
import signal
import sys
import threading
import logging
import random
import json

if len(sys.argv) != 7:
    help = """Usage: python3 {} listener-ip listener-port subnet local-ip port max-ip

    listener-ip     IP address of the connection state listener
    listener-port           Port used by the connection state listener
    subnet          First 3 numbers of IP address (e.g. 10.0.0)
    local-ip        Last number of IP address (e.g. 4)
    port            Port to listen on for incoming connections and to connect to
                        for 'uploads'
    max-ip          Highest value that any address on the subnet uses
    
    For example, if this device had IP address 192.168.1.3, and 
    was connected to devices with address 192.168.1.1 - 192.168.1.10,
    the usage would be
        python3 {} ip port 192.168.1 3 port 10
"""
    print(help.format(sys.argv[0], sys.argv[0]))
    sys.exit(1)

listener_ip = sys.argv[1]
listener_port = int(sys.argv[2])
subnet = sys.argv[3]
local_ip = "{}.{}".format(subnet, sys.argv[4])
server_port = int(sys.argv[5])
max_ip = int(sys.argv[6])

root_log = logging.getLogger("app")
logging.basicConfig(level=logging.INFO, format="%(message)s")

log = logging.getLogger("app.random-uploads")

log.info("Starting random upload bot on {}:{} talking to {}.1:{} - {}.{}:{}".format(local_ip, server_port, subnet, server_port, subnet, max_ip, server_port))

running = True

clients = []

def cleanup():
    server.stop()
    
    for client in clients:
        client.stop()
        client.join()

    global running
    running = False


def signal_handler(sig, frame):
    cleanup()
    time.sleep(1)
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

class ConnectionNotifier:
    """
    Class to notify pox listener when connections go up/down
    Assumed port 6634
    """
    def __init__(self):
        self.__poller = ConnectionPoller()
        self.__poll_thread = ConnectionPollerThread(self.__poller)
        self.__poll_thread.start()
        
        self.__connection = UDPPublisher(listener_ip, listener_port, self.__closed)
        self.__poller.add_connection(self.__connection)
            
    def __closed(self, socket):
        self.__connection = None
        self.__poll_thread.stop()

    def stop(self):
        self.__poller.close_all_connections()
        self.__poll_thread.join()
        
    def send_start_connection(self, target_ip):
        msg = {"src":local_ip, "dest":target_ip, "state":"open"}
        self.__connection.send(json.dumps(msg).encode())  

    def send_stop_connection(self, target_ip):
        msg = {"src":local_ip, "dest":target_ip, "state":"close"}
        self.__connection.send(json.dumps(msg).encode())  

class Server:
    def __init__(self, addr="localhost", port=9000):
        log.info("Starting server...")
        self.__server = TCPServer(addr, port, self.__got_connection)
        self.__connections = []

        log.debug("Starting server poller...")
        self.__poller = ConnectionPoller()
        self.__poll_thread = ConnectionPollerThread(self.__poller)
        self.__poll_thread.start()

    def __got_connection(self, server_socket, address):
        log.info("New connection from" + str(address))

        conn_if = TCPServerConnection(
            server_socket, address, None, self.__connection_closed
        )
        self.__poller.add_connection(conn_if)

    def __connection_closed(self, connection):
        log.info("Server connection closed:" + str(connection.address()))
        self.__poller.remove_connection(connection)
        
    def start(self):
        self.__server.start()

    def stop(self):
        log.info("Stopping server")
        self.__server.stop()
        self.__server.join()
        
        log.debug("Closing connections")
        self.__poller.close_all_connections()
        time.sleep(1)
        
        log.debug("Stopping poller")
        self.__poll_thread.stop()
        self.__poll_thread.join()
       
        log.debug("Stopped")


class Client(Thread):
    def __init__(self, addr="localhost", port=9000, notifier=None):
        super().__init__()
        self.__random = random.Random()
        self.__addr = addr
        self.__port = port
        self.__done = False
        self.__notifier = connection_notifier
        
        global clients
        clients.append(self)

    def __closed(self, connection):
        self.__poll_thread.stop()
        self.__done = True
        log.info("Client side closed; {} clients still open".format(len(clients)))

    def run(self):
        self.__shutdown = False

        log.info("Starting upload to {}:{}...".format(self.__addr, self.__port))
        try:
            self.__poller = ConnectionPoller()
            self.__poll_thread = ConnectionPollerThread(self.__poller)
            self.__connection = TCPClientConnection(self.__addr, self.__port, None, self.__closed)

            self.__poller.add_connection(self.__connection)
            self.__poll_thread.start()

            if self.__notifier:
                self.__notifier.send_start_connection(self.__addr)
                time.sleep(1)

            total_bytes = 0;
            num_writes = self.__random.randint(50, 200)
            for i in range(num_writes):
                if self.__shutdown:
                    break
                    
                msg_len = self.__random.randint(500, 1000)
                total_bytes = total_bytes + msg_len
                data = "".join([str(self.__random.random()) for _ in range(msg_len)])

                log.debug("Queuing message to send")
                try:
                    self.__connection.send(data.encode())
                except ConnectionIsClosedError:
                    log.warning("Server closed before client finished")
                    break
                
                time.sleep(self.__random.uniform(0, 0.25))

            if self.__notifier:
                self.__notifier.send_stop_connection(self.__addr)
                time.sleep(1)
            
            log.info("Uploaded {} bytes to {}:{}".format(total_bytes, self.__addr, self.__port))
            log.debug("Closing client")
            self.__poller.close_all_connections()

        except ConnectionRefusedError:
            log.warning("Unable to connect to {}:{}".format(self.__addr, self.__port))
            self.__shutdown = True
            self.__done = True

    def stop(self):
        log.info("Stopping client")
        self.__shutdown = True
        self.__poll_thread.join()

    def done(self):
        return self.__done

server = Server(local_ip, server_port)
server.start()

connection_notifier = ConnectionNotifier()

while running:
    time.sleep(random.randint(5, 10))
    
    for client in clients:
        if client.done():
            client.stop()
            client.join()
            
            clients.remove(client)
    
    if len(clients) < 10:
        c = Client("{}.{}".format(subnet, random.randint(1, max_ip)), server_port, connection_notifier)
        c.start()
    
    
cleanup()

