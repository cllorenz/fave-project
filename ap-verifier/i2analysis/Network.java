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

import java.io.*;
import java.util.*;
import common.*;



public class Network {
	BDDACLWrapper bddengine;
	String name;
	HashMap<String, Device> devices;

	// device|port - device|port
	HashMap<PositionTuple, PositionTuple> topology;
	//ArrayList<ArrayList<ACLRule>> acllib;
	APComputer fwdapc;

	public PositionTuple LinkTransfer(PositionTuple pt)
	{
		//System.out.println();
		return topology.get(pt);
	}
	
	public HashMap<PositionTuple, PositionTuple> get_topology()
	{
		return topology;
	}

	public Device getDevice(String dname)
	{
		return devices.get(dname);
	}
	
	public Collection<Device> getAllDevices()
	{
		return devices.values();
	}
	
	public Set<PositionTuple> getallactiveports()
	{
		return topology.keySet();
	}
	
	public APComputer getFWDAPC()
	{
		return fwdapc;
	}
	
	public Network(String name, BDDACLWrapper baw) throws IOException
	{
		this.name = name;
		
		devices = new HashMap<String, Device>();
		
		String foldername2 = "i2/";
		String [] devicenames = {"atla","chic","hous","kans","losa","newy32aoa","salt","seat","wash"};
		for( int i = 0; i < devicenames.length; i ++)
		{
			Device d = BuildNetwork.parseDevice(devicenames[i], foldername2 + devicenames[i] + "ap");

			System.out.println(d.name);
			devices.put(d.name, d);
		}
		
		Runtime r = Runtime.getRuntime();
		r.gc();
		r.gc();
		long m1 = r.totalMemory() - r.freeMemory();
		
		bddengine = baw;

		Device.setBDDWrapper(bddengine);
		
		for(Device d : devices.values())
		{
			d.computeFWBDDs();
			
		}
		
		ArrayList<Integer> fwdbddary = new ArrayList<Integer> ();
		
		/*
		for(Device d : devices.values())
		{
			Collection<Integer> bdds = d.getRawACLinUse();
			for(int bdd : bdds)
			{
				fwdbddary.add(bdd);
			}
		}*/
		
		for(Device d : devices.values())
		{
			Collection<Integer> bdds = d.getfwbdds();
			for(int bdd : bdds)
			{
				fwdbddary.add(bdd);
			}
			
		}
		
		
		
		
		
		fwdapc = new APComputer(fwdbddary, bddengine);
		FWDAPSet.setUniverse(fwdapc.getAllAP());
		for(Device d : devices.values())
		{
			d.setaps(fwdapc);
		}

		/*
		 * topology information
		 */
		topology = new HashMap<PositionTuple, PositionTuple>();
		
		addTopology("chic","xe-0/1/0","newy32aoa","xe-0/1/3");
		addTopology("chic","xe-1/0/1","kans","xe-0/1/0");
		addTopology("chic","xe-1/1/3","wash","xe-6/3/0");
		addTopology("hous","xe-3/1/0","losa","ge-6/0/0");
		addTopology("kans","ge-6/0/0","salt","ge-6/1/0");
		addTopology("chic","xe-1/1/2","atla","xe-0/1/3");
		addTopology("seat","xe-0/0/0","salt","xe-0/1/1");
		addTopology("chic","xe-1/0/2","kans","xe-0/0/3");
		addTopology("hous","xe-1/1/0","kans","xe-1/0/0");
		addTopology("seat","xe-0/1/0","losa","xe-0/0/0");
		addTopology("salt","xe-0/0/1","losa","xe-0/1/3");
		addTopology("seat","xe-1/0/0","salt","xe-0/1/3");
		addTopology("newy32aoa","et-3/0/0-0","wash","et-3/0/0-0");
		addTopology("newy32aoa","et-3/0/0-1","wash","et-3/0/0-1");
		addTopology("chic","xe-1/1/1","atla","xe-0/0/0");
		addTopology("losa","xe-0/1/0","seat","xe-2/1/0");
		addTopology("hous","xe-0/1/0","losa","ge-6/1/0");
		addTopology("atla","xe-0/0/3","wash","xe-1/1/3");
		addTopology("hous","xe-3/1/0","kans","ge-6/2/0");
		addTopology("atla","ge-6/0/0","hous","xe-0/0/0");
		addTopology("chic","xe-1/0/3","kans","xe-1/0/3");
		addTopology("losa","xe-0/0/3","salt","xe-0/1/0");
		addTopology("atla","ge-6/1/0","hous","xe-1/0/0");
		addTopology("atla","xe-1/0/3","wash","xe-0/0/0");
		addTopology("chic","xe-2/1/3","wash","xe-0/1/3");
		addTopology("atla","xe-1/0/1","wash","xe-0/0/3");
		addTopology("kans","xe-0/1/1","salt","ge-6/0/0");
		addTopology("chic","xe-1/1/0","newy32aoa","xe-0/0/0");
				
		r.gc();
		r.gc();
		long m2 = r.totalMemory() - r.freeMemory();
		System.out.println("Memory: " + (m2 - m1));
	}

	public Network(String name) throws IOException
	{
		this.name = name;
		
		devices = new HashMap<String, Device>();
		
		String foldername2 = "i2/";
		String [] devicenames = {"atla","chic","hous","kans","losa","newy32aoa","salt","seat","wash"};
		for( int i = 0; i < devicenames.length; i ++)
		{
			Device d = BuildNetwork.parseDevice(devicenames[i], foldername2 + devicenames[i] + "ap");

			System.out.println(d.name);
			devices.put(d.name, d);
		}
		
		Runtime r = Runtime.getRuntime();
		r.gc();
		r.gc();
		long m1 = r.totalMemory() - r.freeMemory();
		
		bddengine = new BDDACLWrapper();

		Device.setBDDWrapper(bddengine);
		
		
		
		for(Device d : devices.values())
		{
			long t1 = System.nanoTime();
			
			d.computeFWBDDs();
			
			long t2 = System.nanoTime();
			System.out.println(d.name + " computing bdds takes " + (t2 - t1) + "ns");
		}
		// do twice
		for(Device d : devices.values())
		{
			long t1 = System.nanoTime();
			
			d.computeFWBDDs();
			
			long t2 = System.nanoTime();
			System.out.println(d.name + " computing bdds takes " + (t2 - t1) + "ns");
		}
		
		
		ArrayList<Integer> fwdbddary = new ArrayList<Integer> ();
		
		/*
		for(Device d : devices.values())
		{
			Collection<Integer> bdds = d.getRawACLinUse();
			for(int bdd : bdds)
			{
				fwdbddary.add(bdd);
			}
		}*/
		
		for(Device d : devices.values())
		{
			Collection<Integer> bdds = d.getfwbdds();
			for(int bdd : bdds)
			{
				fwdbddary.add(bdd);
			}
			
		}
		
		
		
		
		
		fwdapc = new APComputer(fwdbddary, bddengine);
		FWDAPSet.setUniverse(fwdapc.getAllAP());
		for(Device d : devices.values())
		{
			d.setaps(fwdapc);
		}

		/*
		 * topology information
		 */
		topology = new HashMap<PositionTuple, PositionTuple>();
		
		addTopology("chic","xe-0/1/0","newy32aoa","xe-0/1/3");
		addTopology("chic","xe-1/0/1","kans","xe-0/1/0");
		addTopology("chic","xe-1/1/3","wash","xe-6/3/0");
		addTopology("hous","xe-3/1/0","losa","ge-6/0/0");
		addTopology("kans","ge-6/0/0","salt","ge-6/1/0");
		addTopology("chic","xe-1/1/2","atla","xe-0/1/3");
		addTopology("seat","xe-0/0/0","salt","xe-0/1/1");
		addTopology("chic","xe-1/0/2","kans","xe-0/0/3");
		addTopology("hous","xe-1/1/0","kans","xe-1/0/0");
		addTopology("seat","xe-0/1/0","losa","xe-0/0/0");
		addTopology("salt","xe-0/0/1","losa","xe-0/1/3");
		addTopology("seat","xe-1/0/0","salt","xe-0/1/3");
		addTopology("newy32aoa","et-3/0/0-0","wash","et-3/0/0-0");
		addTopology("newy32aoa","et-3/0/0-1","wash","et-3/0/0-1");
		addTopology("chic","xe-1/1/1","atla","xe-0/0/0");
		addTopology("losa","xe-0/1/0","seat","xe-2/1/0");
		addTopology("hous","xe-0/1/0","losa","ge-6/1/0");
		addTopology("atla","xe-0/0/3","wash","xe-1/1/3");
		addTopology("hous","xe-3/1/0","kans","ge-6/2/0");
		addTopology("atla","ge-6/0/0","hous","xe-0/0/0");
		addTopology("chic","xe-1/0/3","kans","xe-1/0/3");
		addTopology("losa","xe-0/0/3","salt","xe-0/1/0");
		addTopology("atla","ge-6/1/0","hous","xe-1/0/0");
		addTopology("atla","xe-1/0/3","wash","xe-0/0/0");
		addTopology("chic","xe-2/1/3","wash","xe-0/1/3");
		addTopology("atla","xe-1/0/1","wash","xe-0/0/3");
		addTopology("kans","xe-0/1/1","salt","ge-6/0/0");
		addTopology("chic","xe-1/1/0","newy32aoa","xe-0/0/0");
				
		r.gc();
		r.gc();
		long m2 = r.totalMemory() - r.freeMemory();
		System.out.println("Memory: " + (m2 - m1));
	}
	
	public void addTopology(String d1, String p1, String d2, String p2)
	{
		PositionTuple pt1 = new PositionTuple(d1, p1);
		PositionTuple pt2 = new PositionTuple(d2, p2);
		// links are two way
		topology.put(pt1, pt2);
		topology.put(pt2, pt1);
	}

	public static void main (String[] args) throws IOException
	{
		Network n = new Network("i2");
		System.out.println(n.topology.size());
	}

}
