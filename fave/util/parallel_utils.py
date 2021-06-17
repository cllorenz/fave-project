import os
import re

import netplumber.jsonrpc as jsonrpc

def stop_all_np_instances():
    print("Stopping all NP instances")
    socklist = get_socklist()
    for sock in socklist:
        try:
            jsonrpc.stop(sock)
            print("Successfully stopped instance: {}".format(sock))
        except Exception as e:
            print("Could not stop socket {}: {}".format(sock, repr(e)))
            

def get_socklist():
  """ Connects sockets to all running netplumber instances
  """
  # open sockets to multiple netplumber instances on the given hosts
  serverlist = get_serverlist()
  try:
    socklist = [jsonrpc.connect_to_netplumber(server['host'], server['port']) for server in serverlist]
    print("Socklist:", socklist)
    if len(socklist) == 0: raise Exception('No netplumber instances found')
    return socklist
  except Exception as e:
    raise Exception('get_socklist(): could not connect all sockets: {}'.format(repr(e)))


def get_serverlist():
  """ Builds list of host addresses for all running netplumber instances
  """

  start_port = int(os.environ['start_port'])
  end_port = int(os.environ['end_port'])
  portlist = [port for port in range(start_port, end_port + 1)]

  serverlist = []

  nodelist = os.environ['SLURM_JOB_NODELIST']
  print(nodelist)
  master_node_id = os.environ['slurm_node_id'] # assumes no instances on master node

  nodes = set(parse_slurm_nodelist(nodelist))
  #nodes.remove(master_node_id)

  for node in nodes:
    for port in portlist:
      serverlist.append({'host': node, 'port': port})
  
  return serverlist


def parse_slurm_nodelist(nodelist):
  nodes = []
  next_delim = ''
  while next_delim != ']':
    next_id, next_delim, nodelist = get_next_node_id_and_delim(nodelist)    
    if next_delim == ',':
      nodes.append("node{}".format(next_id))
      end_id, next_delim, nodelist = get_next_node_id_and_delim(nodelist)
      nodes.append("node{}".format(end_id))
      continue
    if next_delim == '-':
      start_id = next_id
      end_id, next_delim, nodelist = get_next_node_id_and_delim(nodelist)
      for node_id in range(int(start_id), int(end_id) + 1):
        nodes.append("node{}".format(node_id))
      continue
    if next_delim == '':
      nodes.append("node{}".format(next_id))
      break
    if next_delim != ']':
      raise Exception('parse_slurm_nodelist(): Unexpected character in nodelist: {}'.format(next_delim))

  return nodes


def get_next_node_id_and_delim(nodelist):
  next_int_match = re.search(r'\d+', nodelist)
  remaining_string = nodelist[next_int_match.span()[1]:]
  try:
    next_char = remaining_string[0]
  except:
    return next_int_match.group(), '', '' 
  return next_int_match.group(), next_char, remaining_string
