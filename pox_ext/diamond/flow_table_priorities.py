# By default, all messages get flooded and sent to port 1
# and forward it to this controller so it can learn mac addresses
PRIORITY_FLOOD_FORWARD_ALWAYS = 1

# But actually, if it's from port 2 or port 1, we don't forward to port 1
# but we still forward to controller so it can learn what's across
# the diamond
PRIORITY_FLOOD_IF_PORT = 2

# If it's from a mac address we know
# send it to either all local ports and port 1 or
# just all local ports, depending on where the mac address is
PRIORITY_SEND_FROM_MAC = 3

# If it's a broadcast message, send it to all local and port 1
PRIORITY_BROADCAST_FROM_LOCAL = 253

# But actually if it's from port 1 or 2, just flood it to local
PRIORITY_BROADCAST_FROM_OTHER = 254

# If it's for a mac address we know, send it there
PRIORITY_SEND_TO_MAC = 255

# If we're fast-tracking a connection, that takes priority
# for outgoing
PRIORITY_ROUTE_CONNECTION = 256

