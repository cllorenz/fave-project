/*
 * Atomic Predicates Verifier
 * 
 * Copyright (c) 2013 UNIVERSITY OF TEXAS AUSTIN. All rights reserved. Developed
 * by: HONGKUN YANG and SIMON S. LAM http://www.cs.utexas.edu/users/lam/NRL/
 * 
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * with the Software without restriction, including without limitation the
 * rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
 * sell copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * 
 * 1. Redistributions of source code must retain the above copyright notice,
 * this list of conditions and the following disclaimers.
 * 
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimers in the documentation
 * and/or other materials provided with the distribution.
 * 
 * 3. Neither the name of the UNIVERSITY OF TEXAS AUSTIN nor the names of the
 * developers may be used to endorse or promote products derived from this
 * Software without specific prior written permission.
 * 
 * 4. Any report or paper describing results derived from using any part of this
 * Software must cite the following publication of the developers: Hongkun Yang
 * and Simon S. Lam, Real-time Verification of Network Properties using Atomic
 * Predicates, IEEE/ACM Transactions on Networking, April 2016, Volume 24, No.
 * 2, pages 887-900 (first published March 2015, Digital Object Identifier:
 * 10.1109/TNET.2015.2398197).
 * 
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * CONTRIBUTORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS WITH
 * THE SOFTWARE.
 */

package i2analysis;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.Map.Entry;

import common.BDDACLWrapper;
import common.FWDAPSet;
import common.PositionTuple;

/**
 * Used for experimentations of link updates. 
 */
public class ReachabilityGraph {

	StateNode startstate;
	Network net;

	HashMap<String, HashSet<PositionTuple>> devicemap;
	HashMap<PositionTuple, HashSet<StateNode>> reachsets;

	HashMap<String, HashSet<PositionTuple>> changeddevicemap;
	HashMap<PositionTuple, HashSet<StateNode>> changedreachsets;

	HashMap<PositionTuple, PositionTuple> topology;

	public ReachabilityGraph(Network net)
	{
		this.net = net;
		topology = net.topology;
	}
	
	public void setTopology(HashMap<PositionTuple, PositionTuple> top)
	{
		topology = top;
	}

	public PositionTuple LinkTransfer(PositionTuple pt)
	{
		//System.out.println();
		return topology.get(pt);
	}

	public void setStartstate(PositionTuple startpt)
	{
		startstate = new StateNode(startpt, new FWDAPSet(BDDACLWrapper.BDDTrue));
		devicemap = new HashMap<String, HashSet<PositionTuple>>();
		reachsets = new HashMap<PositionTuple, HashSet<StateNode>>();
	}
	
	public void updatedevicemap_d()
	{
		for(String dname : changeddevicemap.keySet())
		{
			if(devicemap.containsKey(dname))
			{
				devicemap.get(dname).removeAll(changeddevicemap.get(dname));
			}else
			{
				System.err.println("not consistent in devicemap.");
				System.exit(1);
			}
		}
	}
	
	public void updatedevicemap()
	{
		for(String dname : changeddevicemap.keySet())
		{
			if(devicemap.containsKey(dname))
			{
				devicemap.get(dname).addAll(changeddevicemap.get(dname));
			}else
			{
				devicemap.put(dname, changeddevicemap.get(dname));
			}
		}
	}

	public void addtodevicemap(PositionTuple pt)
	{
		if(devicemap.containsKey(pt.getDeviceName()))
		{
			devicemap.get(pt.getDeviceName()).add(pt);
		}else
		{
			HashSet<PositionTuple> newset = new HashSet<PositionTuple>();
			newset.add(pt);
			devicemap.put(pt.getDeviceName(), newset);
		}
	}
	

	public void addtodevicemap_u(PositionTuple pt)
	{
		if(changeddevicemap.containsKey(pt.getDeviceName()))
		{
			changeddevicemap.get(pt.getDeviceName()).add(pt);
		}else
		{
			HashSet<PositionTuple> newset = new HashSet<PositionTuple>();
			newset.add(pt);
			changeddevicemap.put(pt.getDeviceName(), newset);
		}
	}
	
	public void updatereachsets_d()
	{
		for(PositionTuple pt : changedreachsets.keySet())
		{
			if(reachsets.containsKey(pt))
			{
				reachsets.get(pt).removeAll(changedreachsets.get(pt));
			}else
			{
				System.err.println("not consistent in reachsets.");
				System.exit(1);
			}
		}
	}
	
	public void updatereachsets()
	{
		for(PositionTuple pt : changedreachsets.keySet())
		{
			if(reachsets.containsKey(pt))
			{
				reachsets.get(pt).addAll(changedreachsets.get(pt));
			}else
			{
				reachsets.put(pt, changedreachsets.get(pt));
			}
		}
	}

	public void addtoreachsets(StateNode sn)
	{
		if(reachsets.containsKey(sn.getPosition()))
		{
			reachsets.get(sn.getPosition()).add(sn);
		}else
		{
			HashSet<StateNode> newset = new HashSet<StateNode>();
			newset.add(sn);
			reachsets.put(sn.getPosition(), newset);
		}
	}

	public void addtoreachsets_u(StateNode sn)
	{
		if(changedreachsets.containsKey(sn.getPosition()))
		{
			changedreachsets.get(sn.getPosition()).add(sn);
		}else
		{
			HashSet<StateNode> newset = new HashSet<StateNode>();
			newset.add(sn);
			changedreachsets.put(sn.getPosition(), newset);
		}
	}

	public void addlink(PositionTuple pt1, PositionTuple pt2)
	{
		changeddevicemap = new HashMap<String, HashSet<PositionTuple>>();
		changedreachsets = new HashMap<PositionTuple, HashSet<StateNode>>();
		
		addlink_onedirect(pt1, pt2);
		addlink_onedirect(pt2, pt1);
		
		updatedevicemap();
		updatereachsets();
		
		topology.put(pt1, pt2);
		topology.put(pt2, pt1);
	}
	
	public void deletelink(PositionTuple pt1, PositionTuple pt2)
	{
		changeddevicemap = new HashMap<String, HashSet<PositionTuple>>();
		changedreachsets = new HashMap<PositionTuple, HashSet<StateNode>>();
		
		topology.remove(pt1);
		topology.remove(pt2);
		
		deletelink_onedirect(pt1, pt2);
		deletelink_onedirect(pt2, pt1);
		
		updatedevicemap_d();
		updatereachsets_d();
		
	}
	
	public void addlink_onedirect(PositionTuple pt1, PositionTuple pt2)
	{
		if(devicemap.containsKey(pt1.getDeviceName()))
		{
			HashSet<PositionTuple> pts1 = devicemap.get(pt1.getDeviceName());
			for(PositionTuple pttmp : pts1)
			{
				for(StateNode sntmp: reachsets.get(pttmp))
				{

					StateNode stpt1 = sntmp.findNextState(pt1);
					if(stpt1 != null)
					{
						// link transfer
						StateNode newsn2 = new StateNode(pt2, stpt1.getAPSet());
						stpt1.addNextState(newsn2);
						Traverse_recur_u(newsn2);
					}
				}
			}
		}
	}
	
	public void deletelink_onedirect(PositionTuple pt1, PositionTuple pt2)
	{
		if(devicemap.containsKey(pt1.getDeviceName()))
		{
			HashSet<PositionTuple> pts1 = devicemap.get(pt1.getDeviceName());
			for(PositionTuple pttmp : pts1)
			{
				for(StateNode sntmp : reachsets.get(pttmp))
				{
					StateNode stpt1 = sntmp.findNextState(pt1);
					if(stpt1 != null)
					{
						// link transfer
						StateNode stpt2 = stpt1.findNextState(pt2);
						if(stpt2 != null)
						{
							stpt1.removeNextState(pt2);
							Traverse_recur_d(stpt2);
						}
					}
				}
			}
		}
	}

	public StateNode ForwardedOnePort(StateNode sn, PositionTuple outpt)
	{
		Device d = net.getDevice(outpt.getDeviceName());
		FWDAPSet aps = d.FowrdAction(sn.getPosition().getPortName(), outpt.getPortName(), sn.getAPSet());
		if(aps == null)
		{
			return null;
		}else
		{
			StateNode newsn = new StateNode(outpt, aps);
			sn.addNextState(newsn);
			return newsn;
		}
	}


	public void Traverse( )
	{
		Traverse_recur(startstate);
	}

	/**
	 * 
	 * @param s - packet set and incoming port
	 * @return - next states
	 */
	public ArrayList<StateNode> ForwardedStates(StateNode s)
	{
		ArrayList<StateNode> nxtSs = new ArrayList<StateNode>();

		Device nxtd = net.getDevice(s.getPosition().getDeviceName());
		if(nxtd == null)
		{
			return nxtSs;
		}
		HashMap<String, FWDAPSet> fwdset =  nxtd.FowrdAction(s.getPosition().getPortName(), s.getAPSet());
		if(fwdset.isEmpty())
		{
			return nxtSs;
		}else
		{
			Iterator iter = fwdset.entrySet().iterator();
			//for(String portname : fwdset.keySet())
			while(iter.hasNext())
			{
				Map.Entry<String, FWDAPSet> oneentry = (Entry<String, FWDAPSet>) iter.next();
				PositionTuple fwdedpt = new PositionTuple(s.getPosition().getDeviceName(), oneentry.getKey());
				//State fwdeds = new State(fwdedpt, fwdset.get(portname), nxts.getAlreadyVisited());
				StateNode fwdeds = new StateNode(fwdedpt, oneentry.getValue(), s.getAlreadyVisited());
				s.addNextState(fwdeds);
				if(fwdeds.loopDetected())
				{
				}else
				{
					nxtSs.add(fwdeds);
				}
			}
		}
		return nxtSs;

	}

	public ArrayList<StateNode> linkTransfer(StateNode s)
	{
		ArrayList<StateNode> nxtSs = new ArrayList<StateNode>();
		PositionTuple nxtpt = LinkTransfer(s.getPosition());
		if(nxtpt == null)
		{
			return nxtSs;
		}else
		{		
			FWDAPSet faps = s.getAPSet();
			StateNode nxts = new StateNode(nxtpt,faps, s.getAlreadyVisited());
			s.addNextState(nxts);

			if(nxts.loopDetected())
			{
			} else
			{
				nxtSs.add(nxts);
			}

		}
		return nxtSs;
	}

	public void Traverse_recur(StateNode s)
	{
		//forwarding
		addtodevicemap(s.getPosition());
		addtoreachsets(s);
		ArrayList<StateNode> nxtSf = ForwardedStates(s);
		for(StateNode nxtsf : nxtSf)
		{
			// link transfer
			ArrayList<StateNode> nxtSl = linkTransfer(nxtsf);
			for(StateNode nxtsl : nxtSl)
			{
				
				Traverse_recur(nxtsl);
			}
		}
	}

	public void Traverse_recur_u(StateNode s)
	{
		//forwarding
		addtodevicemap_u(s.getPosition());
		addtoreachsets_u(s);
		ArrayList<StateNode> nxtSf = ForwardedStates(s);
		for(StateNode nxtsf : nxtSf)
		{
			// link transfer
			ArrayList<StateNode> nxtSl = linkTransfer(nxtsf);
			for(StateNode nxtsl : nxtSl)
			{

				Traverse_recur_u(nxtsl);
			}
		}
	}
	
	// no need to compute reachability
	public void Traverse_recur_d(StateNode s)
	{
		addtodevicemap_u(s.getPosition());
		addtoreachsets_u(s);
		Collection<StateNode> nstates = s.getNextStates();
		if(nstates == null)
		{
			return;
		}else
		{
			for(StateNode ns : nstates)
			{
				Collection<StateNode> nnstates = ns.getNextStates();
				if(nnstates == null)
				{
					return;
				}else
				{
					for(StateNode nns : nnstates)
					{
						Traverse_recur_d(nns);
					}
				}
			}
		}
		
	}


	public static void main (String[] args) throws IOException
	{
		Network n = new Network("i2");
		ReachabilityGraph rg = new ReachabilityGraph(n);

		Set<PositionTuple> pts = n.getallactiveports();


		int rep = 100;
		for(PositionTuple pt1 : pts)
		{
			System.out.println(pt1);
			rg.setStartstate(pt1);
			//long start = System.nanoTime();
			//for(int i = 0; i < rep; i ++)
				rg.Traverse();
			//long end = System.nanoTime();
			//System.out.println((end - start)/1.0/rep);
				rg.startstate.printLoop();
		}
		//StateLoop hs = stfer.Traverse(new PositionTuple("bbra_rtr", "te7/3"));
		//hs.printLoop();
		//hs.printState();
	}
}
