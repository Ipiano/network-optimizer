from .connection import ConnectionIf, ConnectionIsClosedError

import socket
import threading
import logging

from socket import socket as make_socket
from threading import Thread

log = logging.getLogger("app.connection.udp")


class UDPPublisher(ConnectionIf):
    """
    Specialization on ConnectionIf for UDP connections
    Will set the socket to be non-blocking on instantiation
    """

    def __init__(self, address, port, close_callback=None):
        super().__init__(None, close_callback)
        self.__socket = make_socket(type=socket.SOCK_DGRAM)
        self.__socket.setblocking(0)
        self.__open = True
        self.__address = address
        self.__port = port

    def _is_open(self):
        return self.__open

    def _close(self):
        self.__socket.shutdown(socket.SHUT_RDWR)
        self.__socket.close()
        self.__open = False


    def _read(self):
        return False, ""

    def _write(self, data):
        if not self.__open:
            raise ConnectionIsClosedError

        try:
            log.info("Sending on UDP {}".format(data.decode()))
            self.__socket.sendto(data, (self.__address, self.__port))
            return True
        except OSError as err:
            self.__open = False
            log.debug("Failed to write; raising from" + str(err))
            raise ConnectionIsClosedError 


