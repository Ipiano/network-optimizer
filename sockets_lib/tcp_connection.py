from .connection import ConnectionIf, ConnectionIsClosedError

import socket
import threading
import logging

from socket import socket as make_socket
from threading import Thread

log = logging.getLogger("app.connection.tcp")


class TCPConnection(ConnectionIf):
    """
    Specialization on ConnectionIf for TCP connections
    Will set the socket to be non-blocking on instantiation
    """

    def __init__(self, raw_socket, receive_callback, close_callback):
        super().__init__(receive_callback, close_callback)
        self.__socket = raw_socket
        self.__socket.setblocking(0)
        self.__open = True

    def _is_open(self):
        return self.__open

    def _close(self):
        self.__socket.shutdown(socket.SHUT_RDWR)
        self.__socket.close()
        self.__open = False

    def _read(self):
        if not self.__open:
            raise ConnectionIsClosedError

        try:
            return True, self.__socket.recv(2048)
        except BlockingIOError:
            return False, ""
        except OSError as err:
            self.__open = False
            log.debug("Failed to read; raising from" + str(err))
            raise ConnectionIsClosedError

    def _write(self, data):
        if not self.__open:
            raise ConnectionIsClosedError

        try:
            self.__socket.sendall(data)
            return True
        except OSError as err:
            self.__open = False
            log.debug("Failed to write; raising from" + str(err))
            raise ConnectionIsClosedError 


class TCPClientConnection(TCPConnection):
    """
    TCP Client connection - instantiates a raw socket and connects
    to the given address/port
    """

    def __init__(self, dest_address, dest_port, receive_callback = None, close_callback = None):
        raw_socket = make_socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_socket.connect((dest_address, dest_port))

        self.__address = (dest_address, dest_port)

        super().__init__(raw_socket, receive_callback, close_callback)

    def address(self):
        return self.__address


class TCPServerConnection(TCPConnection):
    """
    TCP Server Connection - Takes a socket from a TCP Server that is listening
    """

    def __init__(self, server_socket, client_address, receive_callback, close_callback):
        self.__address = client_address

        super().__init__(server_socket, receive_callback, close_callback)

    def address(self):
        return self.__address


class TCPServer(Thread):
    """
    Thread to listen on a TCP socket for incomming connections
    """

    def __init__(self, local_address, local_port, connect_callback, max_connections=1):
        super().__init__()

        self.__server_socket = make_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.__server_socket.bind((local_address, local_port))
        self.__server_socket.listen(max_connections)
        self.__shutdown = False
        self.__cb = connect_callback
        
        self.__address = local_address
        self.__port = local_port

    def stop(self):
        self.__shutdown = True
        
        # Open connection to unblock socket accept()
        dummy = TCPClientConnection(self.__address, self.__port)
        dummy.close()
        
        self.__server_socket.shutdown(socket.SHUT_RDWR)
        self.__server_socket.close()

    def run(self):
        log.debug(str(threading.get_ident()) + " :: Started Thread")
        while not self.__shutdown:
            try:
                server_socket, address = self.__server_socket.accept()
                if not self.__shutdown:
                    self.__cb(server_socket, address)
            except OSError:
                pass

