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

import java.util.HashSet;

public class APSet extends APSet1{

	public APSet(HashSet<Integer> hs) {
		super(hs);
		// TODO Auto-generated constructor stub
	}
	public APSet(int settype) {
		super(settype);
	}
	
	public APSet(APSet aps2)
	{
		super(aps2);
	}
	
	/**
	 * used for test
	 */
	public static HashSet<Integer> arrytoset(int[] arry)
	{
		HashSet<Integer> s1 = new HashSet<Integer>();
		for(int i = 0; i < arry.length; i ++)
		{
			s1.add(arry[i]);
		}
		return s1;
	}
	
	/**
	 * test it
	 */
	public static void main(String[] args)
	{
		HashSet<Integer> unv = new HashSet<Integer>();
		int Msize = 10;
		for(int i = 0; i < Msize; i ++)
		{
			unv.add(i);
		}
		APSet.setUniverse(unv);
		APSet.setcompThreshold(0.4);
		
		HashSet<Integer> anu = new HashSet<Integer>(unv);
		APSet aps0 = new APSet(anu);
		System.out.println(aps0);
		
		int[] sa1 = {0,1,2};
		HashSet<Integer> s1 = APSet.arrytoset(sa1);
		APSet aps1 = new APSet(s1);
		System.out.println(aps1);
		
		int[] sa2 = {0,1,3,6,9,8};
		HashSet<Integer> s2 = APSet.arrytoset(sa2);
		APSet aps2 = new APSet(s2);
		System.out.println(aps2);
		
		int[] sa3 = {2,6,7};
		HashSet<Integer> s3 = APSet.arrytoset(sa3);
		APSet aps3 = new APSet(s3);
		// NN intersect
		aps3.intersect(aps1);
		System.out.println(aps3);
		aps3 = new APSet(APSet.arrytoset(sa3));
		// NN union
		aps3.union(aps1);
		System.out.println(aps3);
		// CN union
		int[] sa4 = {2,5};
		aps3.union(new APSet(APSet.arrytoset(sa4)));
		System.out.println(aps3);
		// CN intersect
		int[] sa5 = {7,9};
		aps3.intersect(new APSet(APSet.arrytoset(sa5)));
		System.out.println(aps3);
		// NC union
		aps3.union(new APSet(APSet.arrytoset(sa2)));
		System.out.println(aps3);
		// NC intersect
		aps1.intersect(aps3);
		System.out.println(aps1);
		// CC union
		aps2 = new APSet(APSet.arrytoset(sa2));
		int [] sa6 = {2,5,6,7,8};
		APSet aps4 = new APSet(APSet.arrytoset(sa6));
		aps4.union(aps2);
		System.out.println(aps4);
		aps4 = new APSet(APSet.arrytoset(sa6));
		aps4.intersect(aps2);
		System.out.println(aps4);
	}

}
