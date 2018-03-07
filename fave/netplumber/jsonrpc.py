#!/usr/bin/env python2

import json

import cProfile

profile = cProfile.Profile()

def profile_method(method):
    def profile_wrapper(*args,**kwargs):
        profile.enable()
        method(*args,**kwargs)
        profile.disable()
    return profile_wrapper

def dump_stats():
    profile.dump_stats("jsonrpc.stats")

def sendrecv(sock,msg):
    sock.sendall(msg)
    #result = sock.recv(1073741824)
    result = sock.recv(536870912)
    return result

def extract_node(msg):
    data = json.loads(msg)
    return data["result"]

def basic_rpc():
    return {"id":"0","jsonrpc":"2.0"}

#@profile_method
def init(sock,length):
    data = basic_rpc()
    data["method"] = "init"
    data["params"] = {"length":length}
    sendrecv(sock,json.dumps(data))

#@profile_method
def destroy(sock):
    data = basic_rpc()
    data["method"] = "destroy"
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_table(sock,t_idx,ports):
    data = basic_rpc()
    data["method"] = "add_table"
    data["params"] = {"id":t_idx,"in":ports}
    sendrecv(sock,json.dumps(data))

#@profile_method
def remove_table(sock,t_idx):
    data = basic_rpc()
    data["method"] = "remove_table"
    data["params"] = {"id":t_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_rule(sock,t_idx,r_idx,in_ports,out_ports,match,mask,rw):
    data = basic_rpc()
    data["method"] = "add_rule"
    data["params"] = {
        "table":t_idx,
        "index":r_idx,
        "in":in_ports,
        "out":out_ports,
        "match":match,
        "mask":mask,
        "rw":rw
    }
    return extract_node(sendrecv(sock,json.dumps(data)))

#@profile_method
def remove_rule(sock,r_idx):
    data = basic_rpc()
    data["method"] = "remove_rule"
    data["params"] = {"node":r_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_link(sock,from_port,to_port):
    data = basic_rpc()
    data["method"] = "add_link"
    data["params"] = {"from_port":from_port,"to_port":to_port}
    sendrecv(sock,json.dumps(data))

#@profile_method
def remove_link(sock,from_port,to_port):
    data = basic_rpc()
    data["method"] = "remove_link"
    data["params"] = {"from_port":from_port,"to_port":to_port}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_source(sock,hs_list,hs_diff,ports):
    data = basic_rpc()
    data["method"] = "add_source"
    if not hs_diff and len(hs_list) == 1:
        data["params"] = {
            "hs":hs_list[0],
            "ports":ports
        }
    else:
        data["params"] = {
            "hs":{
                "list":hs_list,
                "diff":hs_diff
            },
            "ports":ports
        }
    return extract_node(sendrecv(sock,json.dumps(data)))

#@profile_method
def remove_source(sock,s_idx):
    data = basic_rpc()
    data["method"] = "remove_source"
    data["params"] = {"id":s_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_source_probe(sock,ports,mode,filterexp,test):
    data = basic_rpc()
    data["method"] = "add_source_probe"
    data["params"] = {
        "ports":ports,
        "mode":mode,
        "filter":filterexp,
        "test":test
    }
    return extract_node(sendrecv(sock,json.dumps(data)))

#@profile_method
def remove_source_probe(sock,sp_idx):
    data = basic_rpc()
    data["method"] = "remove_source_probe"
    data["params"] = {"id":sp_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_slice(sock,nid,ns_list,ns_diff):
    data = basic_rpc()
    data["method"] = "add_slice"
    data["params"] = {
        "id":nid,
        "net_space":{
            "type":"header",
            "list":ns_list,
            "diff":ns_diff
        }
    }
    sendrecv(sock,json.dumps(data))

#@profile_method
def remove_slice(sock,nid):
    data = basic_rpc()
    data["method"] = "remove_slice"
    data["params"] = {"id":nid}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_fw_rule(sock,t_idx,r_idx,in_ports,out_ports,fw_match):
    data = basic_rpc()
    data["method"] = "add_fw_rule"
    data["params"] = {
        "table":t_idx,
        "index":r_idx,
        "in_ports":in_ports,
        "out_ports":out_ports,
        "fw_match":fw_match
    }
    return extract_node(sendrecv(sock,json.dumps(data)))

#@profile_method
def remove_fw_rule(sock,r_idx):
    data = basic_rpc()
    data["method"] = "remove_fw_rule"
    data["params"] = {"node":r_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_policy_rule(sock,r_idx,match,action):
    data = basic_rpc()
    data["method"] = "add_policy_rule"
    data["params"] = {"index":r_idx,"match":match,"action":action}
    sendrecv(sock,json.dumps(data))

#@profile_method
def remove_policy_rule(sock,r_idx):
    data = basic_rpc()
    data["method"] = "remove_policy_rule"
    data["params"] = {"index":r_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def add_policy_probe(sock,ports):
    data = basic_rpc()
    data["method"] = "add_policy_probe"
    data["params"] = {"ports":ports}
    return extract_node(sendrecv(sock,json.dumps(data)))

#@profile_method
def remove_policy_probe(sock,pp_idx):
    data = basic_rpc()
    data["method"] = "remove_policy_probe"
    data["params"] = {"node":pp_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def print_table(sock,t_idx):
    data = basic_rpc()
    data["method"] = "print_table"
    data["params"] = {"id":t_idx}
    sendrecv(sock,json.dumps(data))

#@profile_method
def print_topology(sock):
    data = basic_rpc()
    data["method"] = "print_topology"
    data["params"] = None
    sendrecv(sock,json.dumps(data))

#@profile_method
def print_plumbing_network(sock):
    data = basic_rpc()
    data["method"] = "print_plumbing_network"
    data["params"] = None
    sendrecv(sock,json.dumps(data))

#@profile_method
def reset_plumbing_network(sock):
    data = basic_rpc()
    data["method"] = "reset_plumbing_network"
    data["params"] = None
    sendrecv(sock,json.dumps(data))

#@profile_method
def expand(sock,new_length):
    data = basic_rpc()
    data["method"] = "expand"
    data["params"] = {"length":new_length}
    sendrecv(sock,json.dumps(data))

#@profile_method
def dump_plumbing_network(sock,odir):
    data = basic_rpc()
    data["method"] = "dump_plumbing_network"
    data["params"] = { "dir" : odir }
    sendrecv(sock,json.dumps(data))
