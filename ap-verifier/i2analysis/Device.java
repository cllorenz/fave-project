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

import java.util.*;
import common.*;

public class Device {
	static BDDACLWrapper baw;
	String name;
	// acl name to its id in acllib
	ArrayList<ForwardingRule> fws;
	HashMap <String, Integer> fwbdds;
	HashMap <String, FWDAPSet> fwaps;

	public String get_name()
	{
		return name;
	}
	
	public HashMap <String, Integer> get_fwbdds_map ()
	{
		return fwbdds;
	}
	
	public HashMap <String, FWDAPSet> get_fwaps_map()
	{
		return fwaps;
	}

	public Device(String dname)
	{
		this.name = dname;
		fws = new ArrayList<ForwardingRule>();
	}

	public void show_fwd_bddsize()
	{
		System.out.println(name);
		int total_size = 0;
		for(Integer one_p : fwbdds.values())
		{
			total_size = total_size + baw.getNodeSize(one_p);
		}
		System.out.println(total_size);
	}


	public static void setBDDWrapper(BDDACLWrapper baw)
	{
		Device.baw = baw;
	}


	/**
	 * 
	 * @param port
	 * @param fwdaps
	 * @return <portname, ap set>
	 */
	public HashMap <String, FWDAPSet> FowrdAction(String port, FWDAPSet fwdaps)
	{
		HashMap <String, FWDAPSet> fwded = new HashMap<String, FWDAPSet>();


		//System.out.println(fwaps.keySet());

		Iterator iter = fwaps.entrySet().iterator();
		while(iter.hasNext())
		{
			Map.Entry entry = (Map.Entry) iter.next();
			String otherport = (String) entry.getKey();
			//
			if(!otherport.equals(port))
			{
				FWDAPSet fwtmp1 = new FWDAPSet(fwdaps);
				fwtmp1.intersect((FWDAPSet) entry.getValue());
				if(!fwtmp1.isempty())
				{

					fwded.put(otherport, fwtmp1);					

				}
			}
		}

		return fwded;
	}

	public FWDAPSet FowrdAction(String inport, String outport, FWDAPSet fwdaps)
	{
		if(fwaps.containsKey(outport))
		{
			FWDAPSet fwtmp = new FWDAPSet(fwdaps);
			fwtmp.intersect(fwaps.get(outport));
			if(fwtmp.isempty())
			{
				return null;
			}else
			{
				return fwtmp;
			}
		}else
		{
			return null;
		}
	}

	/**
	 * forwarding, acls
	 * @param apc
	 */
	public void setaps(APComputer apc)
	{
		fwaps = new HashMap <String, FWDAPSet>();

		setaps_1(fwaps, fwbdds, apc);

	}

	private void setaps_1(HashMap<String, FWDAPSet> filteraps, 
			HashMap<String, Integer> filterbdds, APComputer apc)
	{
		for(String portname : filterbdds.keySet())
		{
			HashSet<Integer> rawset = apc.getAPExpComputed(filterbdds.get(portname));
			if(rawset == null)
			{
				System.err.println("bdd expression not found!");
				System.exit(1);
			}else
			{
				FWDAPSet faps = new FWDAPSet(rawset);
				filteraps.put(portname, faps);
			}
		}
	}

	public Collection<Integer> getfwbdds()
	{
		return fwbdds.values();
	}

	public Collection<FWDAPSet> getfwaps()
	{
		return fwaps.values();
	}

	public void computeFWBDDs()
	{
		Collections.sort(fws);
		this.fwbdds = Device.baw.getfwdbdds_sorted_no_store(fws);
		//this.fwbdds = Device.baw.getfwdbdds(fws);
		
		//System.out.println(fwbdds.size());
		//for(String iname : fwbdds.keySet())
		//{
		//	System.out.println(iname + ": " + fwbdds.get(iname));
		//}
	}

	public void addFW(ForwardingRule fw)
	{
		fws.add(fw);
	}




}
