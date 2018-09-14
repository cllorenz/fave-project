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

package common;

import java.util.ArrayList;
import java.util.HashSet;

/**
 * a state is (a place in the network, packet set)
 */

public class StateBDD {

	public static final int contflag = 0;
	public static final int destflag = 1;
	public static final int loopflag = 2;
	public static final int deadflag = 3;

	PositionTuple pt;
	int ps;
	int flag;
	ArrayList<StateBDD> nextState;
	/*
	 * ports have traveled prior to the current position
	 */
	//HashSet<PositionTuple> visited;
	/*
	 * device have traveled prior to the current position
	 */
	HashSet<String> dvisited;

	public StateBDD(PositionTuple pt, int ps)
	{
		this.pt = pt;
		this.ps = ps;
		dvisited = new HashSet<String>();
		flag = deadflag;
		nextState = null;
	}

	public StateBDD(PositionTuple pt, int apt, HashSet<String> visitedset)
	{
		this.pt = pt;
		this.ps = apt;
		dvisited = visitedset;
		flag = deadflag;
		nextState = null;
	}

	public int getAPTuple()
	{
		return ps;
	}

	public PositionTuple getPosition()
	{
		return pt;
	}

	public void addNextState(StateBDD s)
	{
		if(nextState == null)
		{
			nextState = new ArrayList<StateBDD>();
			flag = contflag;
		}
		nextState.add(s);

	}

	public HashSet<String> getVisited()
	{
		return dvisited;
	}

	public HashSet<String> getAlreadyVisited()
	{
		HashSet<String> alv = new HashSet<String> (dvisited);
		alv.add(pt.getDeviceName());
		return alv;
	}

	public boolean loopDetected()
	{
		if(dvisited.contains(pt.getDeviceName()))
		{
			flag = loopflag;
			return true;
		}else
		{
			return false;
		}
	}

	public boolean destDetected(PositionTuple destpt)
	{
		if(pt.equals(destpt))
		{
			flag = destflag;
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
		case destflag: 
			return "dest";
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
		String newheadstr = headstr + pt + " " + ps + " ";
		if(nextState == null)
		{
			System.out.println(newheadstr + printFlag());
		}else
		{
			for(int i = 0; i < nextState.size(); i ++)
			{
				StateBDD nxtS = nextState.get(i);
				nxtS.printState_recur(newheadstr);
			}
		}
		
	}

}
