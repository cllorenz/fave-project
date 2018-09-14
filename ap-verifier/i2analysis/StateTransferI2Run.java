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
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

import common.PositionTuple;
import common.State;


public class StateTransferI2Run {

	/**
	 * 
	 * @param args - 1,2,3
	 * @throws IOException
	 */
	public static void main(String[] args) throws IOException
	{
		Network n = new Network("i2");
		StateTransfer stfer = new StateTransfer(n);
		Set<PositionTuple> pts = n.getallactiveports();
		Iterator<PositionTuple> ptiter = pts.iterator();
		int cntr = 0;
		HashSet<PositionTuple> ptsh1 = new HashSet<PositionTuple>();
		HashSet<PositionTuple> ptsh2 = new HashSet<PositionTuple>();
		HashSet<PositionTuple> ptsh3 = new HashSet<PositionTuple>();
		while(cntr < pts.size()/3)
		{
			ptsh1.add(ptiter.next());
			cntr ++;
		}
		while(cntr < pts.size() /3 *2)
		{
			ptsh2.add(ptiter.next());
			cntr ++;
		}
		while(ptiter.hasNext())
		{
			ptsh3.add(ptiter.next());
		}
		
		int choice = Integer.parseInt(args[0]);
		HashSet<PositionTuple> apts = null;
		if(choice == 1)
		{
			apts = ptsh1;
		}else if(choice == 2)
		{
			apts = ptsh2;
		}else
		{
			apts = ptsh3;
		}
		
		System.out.println(apts.size());
		
		for(PositionTuple pt1 : apts)
			for(PositionTuple pt2 : pts)
			{
				if(!pt1.equals(pt2))
				{
					long start = System.nanoTime();
					int rep = 10000;
					for(int i = 0; i < rep; i ++)
					{
						State hs = stfer.Traverse(pt1, pt2);
						//State hs = stfer.Traverse(new PositionTuple("gozb_rtr","te2/3"), new PositionTuple("bbra_rtr","te7/3"));
					}
					long end = System.nanoTime();
					System.out.println((end - start)/1000000.0/rep);
				}
			}
		

	}
}
