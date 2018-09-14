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
import java.util.HashMap;
import common.PositionTuple;

public class AddLinkRun {
	Network net;
	HashMap<PositionTuple, PositionTuple> topology;


	public AddLinkRun(Network n)
	{
		net = n;
		topology = n.topology;
	}

	public double TestAdd(HashMap<PositionTuple, PositionTuple> top, PositionTuple startpt, PositionTuple ta1, PositionTuple ta2)
	{
		int rep = 2000;

		long start = System.nanoTime();
		for(int i = 0; i < rep; i ++)
		{
			ReachabilityGraph rg = new ReachabilityGraph(net);
			rg.setTopology((HashMap<PositionTuple, PositionTuple>) top.clone());
			rg.setStartstate(startpt);
			rg.Traverse();
			rg.addlink(ta1, ta2);
		}
		long middle = System.nanoTime();

		for(int i = 0; i < rep; i ++)
		{
			ReachabilityGraph rg = new ReachabilityGraph(net);
			rg.setTopology((HashMap<PositionTuple, PositionTuple>) top.clone());
			rg.setStartstate(startpt);
			rg.Traverse();
		}
		long end = System.nanoTime();
		long t1 = middle - start;
		long t2 = end - middle;
		
		return (t1 - t2)/1000000.0/rep;
		
	}
	
	public void TestAdd(HashMap<PositionTuple, PositionTuple> top, PositionTuple ta1, PositionTuple ta2)
	{
		for(PositionTuple startpt : top.keySet())
		{
			double t = TestAdd(top, startpt, ta1, ta2);
			System.out.println(t);
		}
	}
	
	public void TestAdd()
	{
		for(PositionTuple pt1 : topology.keySet())
		{
			PositionTuple pt2 = topology.get(pt1);
			HashMap<PositionTuple, PositionTuple> newtop = (HashMap<PositionTuple, PositionTuple>) topology.clone();
			newtop.remove(pt1);
			newtop.remove(pt2);
			TestAdd(newtop, pt1, pt2);
		}
	}
	
	public static void main(String [] args) throws IOException
	{
		Network n = new Network("i2");
		AddLinkRun alr = new AddLinkRun(n);
		alr.TestAdd();
	}

}
