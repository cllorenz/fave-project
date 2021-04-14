import Queue
import asyncore
import socket
import sys

node_link_queue = Queue.Queue()
node_link_dict = {}

def add_node_to_dict(idx, node):
    try: node_link_dict[idx]
    except: node_link_dict[idx] = {}

    node_link_dict[idx]['node'] = node
    
def add_link_to_dict(idx, link):
    try: node_link_dict[idx]
    except: node_link_dict[idx] = {}

    node_link_dict[idx]['link'] = link

def prepare_node_link_queue():
    for pair in node_link_dict.values():
        node_link_queue.put((pair['node'], pair['link']))

def distribute_nodes_and_links():
    prepare_node_link_queue()
    import util.parallel_utils as parallel_utils
    for server in parallel_utils.get_serverlist():
        print('Creating dispatcher: {}'.format(server))
        sys.stdout.flush()
        NodeLinkDispatcher(server['host'], server['port'])
    asyncore.loop()
    print('LOOP DONE')
    sys.stdout.flush()

class NodeLinkDispatcher(asyncore.dispatcher):
    
    def __init__(self, host, port):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((host, port))

        self.host = host
        self.port = port
        
        # Keep track of expected messages before closing the channel
        self.recv_queue = Queue.Queue()

        # Immediately send a pair on construction
        self.send_next_pair()

        self.raw_msg_buf = ''

    
    def send_next_pair(self):
        try:
            # Try sending a message if there are still open messages
            node_msg, link_msg = node_link_queue.get_nowait()
            print("Sending ({}): {}".format((self.host, self.port), (node_msg, link_msg)))
            # print((node_msg, link_msg))
            self.send(node_msg + '\n')
            self.send(link_msg + '\n')
            # Add "message expected" signal to recv queue
            self.recv_queue.put(node_msg)
            self.recv_queue.put(link_msg)
        except Queue.Empty:
            if self.recv_queue.empty():
                print("Closing send_next_pair {}".format((self.host, self.port)))
                sys.stdout.flush()
                self.close()

    def handle_read(self):
        results = self.recv_whole_buffer()
        for result in results:
            print("Receiving ({}): {}".format((self.host, self.port), result))
            sys.stdout.flush()
            try:
                # Remove one entry for an expected message
                self.recv_queue.get_nowait()
            except Queue.Empty:
                # no messages expected anymore, close the channel
                print("Closing {}".format((self.host, self.port)))
                sys.stdout.flush()
                self.close()
            # channel still open, try sending another message
        self.send_next_pair()
        
    def recv_whole_buffer(self):
        results = []
        raw = self.recv(4096)
        chunk = self.raw_msg_buf + raw
        self.raw_msg_buf = ''

        pos = chunk.rfind('\n')

        if pos == -1:
            self.raw_msg_buf = chunk
            return []

        elif pos != len(chunk) - 1:
            self.raw_msg_buf = chunk[(pos+1):]
            chunk = chunk[:pos]

        results = [m for m in chunk.split('\n') if m]

        return results
