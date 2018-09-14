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

import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;

import common.FWDAPSet;
import common.PositionTuple;

/**
 * a state is (a place in the network, packet set) 
 */

public class StateNode {

	public static final int contflag = 0;
	public static final int loopflag = 2;
	public static final int deadflag = 3;
	// dead branch means that we find a loop not originated from source port

	PositionTuple pt;
	FWDAPSet fwdaps;
	int flag;

	HashMap<PositionTuple, StateNode> nextStateNodes;	

	HashSet<PositionTuple> dvisited;

	public StateNode(PositionTuple pt, FWDAPSet fwdaps)
	{
		this.pt = pt;
		this.fwdaps = fwdaps;
		dvisited = new HashSet<PositionTuple>();
		flag = deadflag;
		nextStateNodes = null;
	}
	
	public Collection<StateNode> getNextStates()
	{
		if(nextStateNodes == null)
		{
			return null;
		}else
		{
			return nextStateNodes.values();
		}
	}

	public StateNode(PositionTuple pt, FWDAPSet fwdaps, HashSet<PositionTuple> visitedset)
	{
		this.pt = pt;
		this.fwdaps = fwdaps;
		dvisited = visitedset;
		flag = deadflag;
		nextStateNodes = null;
	}

	public StateNode findNextState(PositionTuple pt)
	{	
		if(nextStateNodes == null)
		{
			return null;
		}
		return nextStateNodes.get(pt);
	}
	
	public void removeNextState(PositionTuple pt)
	{
		nextStateNodes.remove(pt);
		if(nextStateNodes.isEmpty())
		{
			flag = deadflag;
			nextStateNodes = null;
		}
	}

	public FWDAPSet getAPSet()
	{
		return fwdaps;
	}

	public PositionTuple getPosition()
	{
		return pt;
	}

	public void addNextState(StateNode s)
	{
		if(nextStateNodes == null)
		{
			nextStateNodes = new HashMap<PositionTuple, StateNode>();
			flag = contflag;
		}
		nextStateNodes.put(s.getPosition(), s);

	}

	public HashSet<PositionTuple> getVisited()
	{
		return dvisited;
	}

	public HashSet<PositionTuple> getAlreadyVisited()
	{
		HashSet<PositionTuple> alv = new HashSet<PositionTuple> (dvisited);
		alv.add(pt);
		return alv;
	}

	public boolean loopDetected()
	{
		if(dvisited.contains(pt))
		{
			flag = loopflag;
			return true;
		}else
		{
			return false;
		}
	}

	public String printFlag()
	{
		switch (flag) {
		case contflag: 
			return "cont";
		case loopflag:
			return "loop";
		case deadflag:
			return "dead";
		default: 
			System.err.println("unknown flag " + flag);
			System.exit(1);
		}
		return null;
	}

	/**
	 * depth first print
	 */
	public void printState()
	{
		printState_recur("");
	}

	public void printState_recur(String headstr)
	{
		String newheadstr = headstr + pt + " " + fwdaps + " ";
		if(nextStateNodes == null)
		{
			System.out.println(newheadstr + printFlag());
		}else
		{
			for(StateNode nxtS : nextStateNodes.values())
			{
				nxtS.printState_recur(newheadstr);
			}
		}

	}
	
	public void printLoop()
	{
		printLoop_recur("");
	}
	
	public void printLoop_recur(String headstr)
	{
		String newheadstr = headstr + pt + " " + fwdaps + " ";
		if(flag == loopflag)
		{
			System.out.println(newheadstr + printFlag());
			return;
		}else if(nextStateNodes == null)
		{
			return;
		}
		else
		{
			for(StateNode nxtS : nextStateNodes.values())
			{
				nxtS.printLoop_recur(newheadstr);
			}
		}
	}



}
