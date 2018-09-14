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

package stanalysis;

import java.io.IOException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.Map.Entry;

import common.BDDACLWrapper;
import common.FWDAPSet;
import common.PositionTuple;
import common.State;

public class StateTransfer {

	PositionTuple destination;
	Network net;

	public StateTransfer(Network net)
	{
		this.net = net;
	}

	/**
	 * return the head state
	 */
	public State Traverse(PositionTuple startpt, PositionTuple endpt)
	{
		destination = endpt;
		State startstate = new State(startpt, new FWDAPSet(BDDACLWrapper.BDDTrue));
		Traverse_recur(startstate);
		return startstate;
	}

	public void Traverse_recur(State s)
	{
		PositionTuple curpt = s.getPosition();
		HashSet<PositionTuple> nxtpts = net.LinkTransfer(curpt);
		if(nxtpts == null)
		{
			return;
		}
		for(PositionTuple nxtpt : nxtpts){
			State nxts = null;

			{
				FWDAPSet faps = s.getAPSet();
				nxts = new State(nxtpt,faps, s.getAlreadyVisited());
				s.addNextState(nxts);
			}

			if(nxts.loopDetected())
			{
				return;
			}
			if(nxts.destDetected(destination))
			{
				return;
			}

			// next one is the switch forwarding
			Device nxtd = net.getDevice(nxtpt.getDeviceName());
			if(nxtd == null)
			{
				return;
			}
			FWDAPSet fwdaps = new FWDAPSet(nxts.getAPSet());
			HashMap<String, FWDAPSet> fwdset =  nxtd.FowrdAction(nxtpt.getPortName(), fwdaps);
			if(fwdset.isEmpty())
			{
				return;
			}else
			{
				Iterator iter = fwdset.entrySet().iterator();
				//for(String portname : fwdset.keySet())
				while(iter.hasNext())
				{
					Map.Entry<String, FWDAPSet> oneentry = (Entry<String, FWDAPSet>) iter.next();
					PositionTuple fwdedpt = new PositionTuple(nxtpt.getDeviceName(), oneentry.getKey());
					//State fwdeds = new State(fwdedpt, fwdset.get(portname), nxts.getAlreadyVisited());
					State fwdeds = new State(fwdedpt, oneentry.getValue(), nxts.getAlreadyVisited());
					nxts.addNextState(fwdeds);
					//if(!fwdeds.loopDetected() && !fwdeds.destDetected(destination))
					Traverse_recur(fwdeds);
				}
			}
		}
	}

	public static void main (String[] args) throws IOException
	{
		Network n = new Network("st");
		StateTransfer stfer = new StateTransfer(n);

		Set<PositionTuple> pts = n.getallactiveports();

		State hs = stfer.Traverse(new PositionTuple("bbra_rtr","te7/1"), new PositionTuple("bbrb_rtr","te7/2"));
		hs.printState();

	}
}
