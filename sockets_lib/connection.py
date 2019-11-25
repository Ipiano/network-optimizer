from abc import ABC, abstractmethod
from threading import Thread
from select import select
from queue import Queue

import threading
import time
import logging

log = logging.getLogger("app.connection.internals")


class ConnectionIsClosedError(Exception):
    """
    Exception raised when a read or write is attempted
    while the connection is closed. If this is raised, it is
    assumed that the connection will never be open again
    """

    pass


class ConnectionIf(ABC):
    @abstractmethod
    def _read(self):
        """
        Attempt to read some data, return (success, data)
        For best results, do this in a non-blocking manner, and
        return false if no data available or read fails but may
        not be closed

        Raises ConnectionIsClosedError if not open
        """
        pass

    @abstractmethod
    def _write(self, data):
        """
        Attempt to write some data, return success
        For best results, do this in a non-blocking manner and 
        return false on failure if figure writes may succeed

        Raises ConnectionIsClosedError if not open
        """
        pass

    @abstractmethod
    def _close(self, data):
        pass

    @abstractmethod
    def _is_open(self):
        """
        Return true if the connection has not been closed by either side
        """
        pass

    def __init__(self, receive_callback = None, closed_callback = None, max_reads=None, max_writes=None):
        """
        receive_callback is function with signature void(self, data)
            Called when any data recieved

        closed_callback is function with signature void(self)
            Called during the first poll() after the connection is closed
            on either side

        max_reads is the max number of times to read per poll
        max_writes is the max number of times to write per poll
        """
        self.__rcv_cb = receive_callback
        self.__cls_cb = closed_callback

        self.__reads = max_reads
        self.__writes = max_writes

        self.__pub_queue = Queue()
        self.__buffer = None

        self.__closed = False
        self.__was_closed = False

    def close(self):
        """
        Closes the connection if it is not already closed.
        The connection cannot be reopened unless a new object 
        is instantiated
        """
        if not self.__closed:
            self.__closed = True
            self._close()

    def send(self, data):
        """
        Queues a message to be sent on the socket at the next poll()

        raises ConnectionIsClosedError if the connection has been closed
        """
        if self.__closed:
            raise ConnectionIsClosedError
        self.__pub_queue.put(data)

    def poll(self):
        """
        Attempts to read as up to max_reads, and then attempts to write
        queued messages, up to max_writes.

        After all reading and writing is done, the receive_callback
        will be called for each piece of data received

        If the socket has been closed, the closed_callback will be called
        at the end of the poll
        """
        self.__did_just_close = False
        data_read = []
        log.debug(str(threading.get_ident()) + " :: " + "Poll socket")
        try:
            if not self.__was_closed and (self.__closed or not self._is_open):
                log.debug(str(threading.get_ident()) + " :: " + "Socket just got closed")
                self.__did_just_close = True
                self.__closed = True
                self.__was_closed = True

            if not self.__closed:
                success = True
                reads = 0
                while success:
                    log.debug(str(threading.get_ident()) + " :: " + "Trying to read")
                    success, data = self._read()
                    success = success and len(data) > 0
                    if success:
                        data_read.append(data)

                        reads = reads + 1
                        if self.__reads is not None and reads >= self.__reads:
                            break

                if self.__buffer is None and not self.__pub_queue.empty():
                    self.__buffer = self.__pub_queue.get()

                messages = self.__pub_queue.qsize() + 1 if self.__buffer is not None else 0
                log.debug(
                    str(threading.get_ident())
                    + " :: "
                    + "Trying to publish "
                    + str(messages)
                    + " messages"
                )

                # Figure out how many times to try to publish
                publishes = messages if self.__writes is None else min(messages, self.__writes)

                # Attempt to publish all data, stop if
                # any fails
                while publishes > 0:
                    if self._write(self.__buffer):
                        publishes = publishes - 1
                        self.__buffer = (
                            self.__pub_queue.get() if not self.__pub_queue.empty() else None
                        )
                        log.debug(
                            str(threading.get_ident())
                            + " :: "
                            + str(self.__pub_queue.qsize())
                            + " messages left to send"
                        )
                    else:
                        break
        except ConnectionIsClosedError:
            log.debug(str(threading.get_ident()) + " :: " + "Connection closed!")
            self.__closed = True
            self.__was_closed = True
            self.__did_just_close = True

        log.debug(
            str(threading.get_ident())
            + " :: Handling "
            + str(len(data_read))
            + " messages recieved"
        )
        for data in data_read:
            if self.__rcv_cb:
                self.__rcv_cb(self, data)

        if self.__did_just_close:
            self.__pub_queue = Queue()
            
            if self.__cls_cb:
                self.__cls_cb(self)


class ConnectionPoller:
    """
    Manager for multiple connection objects. Connections
    can be added to and removed from the poller, and it will
    poll them sequentially on each poll()
    """

    def __init__(self):
        self.__connections = set()
        self.__adds = set()
        self.__removes = set()
        self.__lock = threading.Lock()
        self.__update = False

    def size(self):
        with self.__lock:
            return len(self.__connections) + len(self.__adds) - len(self.__removes)

    def add_connection(self, connection_if):
        with self.__lock:
            self.__adds.add(connection_if)
            self.__removes.discard(connection_if)
            self.__update = True

    def remove_connection(self, connection_if):
        with self.__lock:
            self.__adds.discard(connection_if)
            if connection_if in self.__connections:
                self.__removes.add(connection_if)
            self.__update = True

    def close_all_connections(self):
        for connection_if in self.__connections:
            connection_if.close()

    def poll(self):
        if self.__update:
            with self.__lock:
                log.debug(str(threading.get_ident()) + " :: " + "Updating connections to poll")
                self.__connections -= self.__removes
                self.__connections |= self.__adds
                self.__removes.clear()
                self.__adds.clear()
                self.__update = False

        for connection_if in self.__connections:
            connection_if.poll()


class ConnectionPollerThread(Thread):
    """
    Thread to call poll() on a connection or connection
    poller in a loop
    """

    def __init__(self, pollable, poll_rate=10):
        super().__init__()
        self.__pollable = pollable
        self.__shutdown = False
        self.__sleep_time = 1.0 / poll_rate if poll_rate > 0 else 0

    def stop(self):
        self.__shutdown = True

    def is_shutting_down(self):
        return self.__shutdown

    def run(self):
        log.debug(str(threading.get_ident()) + " :: Started Thread")
        while not self.__shutdown:
            self.__pollable.poll()
            log.debug(
                str(threading.get_ident()) + " :: " + "Sleeping for " + str(self.__sleep_time)
            )
            time.sleep(self.__sleep_time)


