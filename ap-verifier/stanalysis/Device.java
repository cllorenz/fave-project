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

import java.util.*;

import common.*;

public class Device {
	static BDDACLWrapper baw;
	String name;
	// acl name to its id in acllib
	HashMap<String, LinkedList<ACLRule>> aclmap;
	HashMap<String, Integer> rawacl;
	HashSet<Integer> rawaclinuse;
	String[] usedacls;
	ArrayList<ForwardingRule> fws;
	// subnet name -> subnet info
	HashMap <String, ArrayList<Subnet>> subnets;
	HashMap<String, HashSet<String>> vlan_ports;
	ArrayList<ACLUse> acluses;
	HashMap <String, Integer> fwbdds;
	HashMap <String, FWDAPSet> fwaps;
	// portname -> acl bdd, should be physical port
	// combined with vlan info
	HashMap<String, Integer> inaclbdds;
	HashMap<String, Integer> outaclbdds;
	HashMap<String, FWDAPSet> inaclaps;
	HashMap<String, FWDAPSet> outaclaps;


	public Device(String dname)
	{
		this.name = dname;
		//ports = new HashMap<String, Port>();
		aclmap = new HashMap<String, LinkedList<ACLRule>>();
		fws = new ArrayList<ForwardingRule>();
		vlan_ports = new HashMap<String, HashSet<String>>();
		acluses = new ArrayList<ACLUse>();
		subnets = new HashMap<String, ArrayList<Subnet>> ();
	}

	public Collection<Integer> getinaclbdds()
	{
		return inaclbdds.values();
	}

	public Collection<Integer> getoutaclbdds()
	{
		return outaclbdds.values();
	}

	public Collection<Integer> getRawACL()
	{
		return rawacl.values();
	}

	public Collection<Integer> getRawACLinUse()
	{
		return rawaclinuse;
	}

	public void computeRawACL()
	{
		rawacl = new HashMap<String, Integer> ();
		for(String aclname : aclmap.keySet())
		{
			rawacl.put(aclname, baw.ConvertACLs(aclmap.get(aclname)));
		}
		//System.out.println(rawacl);
	}
	
	public void computeACLBDDZs()
	{
		computeRawACL();
		rawaclinuse = new HashSet<Integer>();
		HashMap<String, ArrayList<Integer>> inaclbddset = new HashMap<String, ArrayList<Integer>> ();
		HashMap<String, ArrayList<Integer>> outaclbddset = new HashMap<String, ArrayList<Integer>> ();
		for(int i = 0; i < acluses.size(); i ++)
		{
			ACLUse oneacluse = acluses.get(i);
			//System.out.println(oneacluse);
			int rawaclbdd;
			if(rawacl.containsKey(oneacluse.getnumber()))
			{

				rawaclbdd = rawacl.get(oneacluse.getnumber());
				rawaclinuse.add(rawaclbdd);
			}else
			{
				// cannot find the acl
				continue;
			}
			HashSet<String> ports;
			if(vlan_ports.containsKey(oneacluse.getinterface()))
			{
				ports = vlan_ports.get(oneacluse.getinterface());
			}else
			{
				ports = new HashSet<String> ();
				ports.add(oneacluse.getinterface());
			}
			if(oneacluse.isin())
			{
				int aclbdd = baw.encodeACLin(null, rawaclbdd, ports.size());
				//System.out.println(oneacluse);

				for(String pport : ports)
				{
					if(inaclbddset.containsKey(pport))
					{
						inaclbddset.get(pport).add(aclbdd);
					}else
					{
						ArrayList<Integer> newset = new ArrayList<Integer>();
						newset.add(aclbdd);
						inaclbddset.put(pport, newset);
					}
				}
			}else
			{
				int aclbdd = baw.encodeACLout(null, rawaclbdd, ports.size());
				for(String pport : ports)
				{
					if(outaclbddset.containsKey(pport))
					{
						outaclbddset.get(pport).add(aclbdd);
					}else
					{
						ArrayList<Integer> newset = new ArrayList<Integer>();
						newset.add(aclbdd);
						outaclbddset.put(pport, newset);
					}
				}
			}
		}

		inaclbdds = new HashMap<String, Integer>();
		outaclbdds = new HashMap<String, Integer>();
		for(String pport : inaclbddset.keySet())
		{
			ArrayList<Integer> bddset = inaclbddset.get(pport);
			int [] bdds = Utility.ArrayListToArray(bddset);
			//System.out.println(bdds.length);
			int andbdd = baw.AndInBatch(bdds);
			baw.DerefInBatch(bdds);
			inaclbdds.put(pport, andbdd);
		}
		for(String pport : outaclbddset.keySet())
		{
			ArrayList<Integer> bddset = outaclbddset.get(pport);
			int [] bdds = Utility.ArrayListToArray(bddset);
			int andbdd = baw.AndInBatch(bdds);
			baw.DerefInBatch(bdds);
			outaclbdds.put(pport, andbdd);
		}

		//System.out.println("in: " + inaclbdds);
		//System.out.println("out: " + outaclbdds);
	}

	public void computeACLBDDs()
	{
		computeRawACL();
		rawaclinuse = new HashSet<Integer>();
		HashMap<String, ArrayList<Integer>> inaclbddset = new HashMap<String, ArrayList<Integer>> ();
		HashMap<String, ArrayList<Integer>> outaclbddset = new HashMap<String, ArrayList<Integer>> ();
		for(int i = 0; i < acluses.size(); i ++)
		{
			ACLUse oneacluse = acluses.get(i);
			ArrayList<Subnet> subs = subnets.get(oneacluse.getinterface());
			//System.out.println(oneacluse);
			int rawaclbdd;
			if(rawacl.containsKey(oneacluse.getnumber()))
			{

				rawaclbdd = rawacl.get(oneacluse.getnumber());
				rawaclinuse.add(rawaclbdd);
			}else
			{
				// cannot find the acl
				continue;
			}
			HashSet<String> ports;
			if(vlan_ports.containsKey(oneacluse.getinterface()))
			{
				ports = vlan_ports.get(oneacluse.getinterface());
			}else
			{
				ports = new HashSet<String> ();
				ports.add(oneacluse.getinterface());
			}
			if(oneacluse.isin())
			{
				int aclbdd = baw.encodeACLin(subs, rawaclbdd, ports.size());
				//int aclbdd = baw.encodeACLin(null, rawaclbdd, ports.size());
				//System.out.println(oneacluse);

				for(String pport : ports)
				{
					if(inaclbddset.containsKey(pport))
					{
						inaclbddset.get(pport).add(aclbdd);
					}else
					{
						ArrayList<Integer> newset = new ArrayList<Integer>();
						newset.add(aclbdd);
						inaclbddset.put(pport, newset);
					}
				}
			}else
			{
				int aclbdd = baw.encodeACLout(subs, rawaclbdd, ports.size());
				//int aclbdd = baw.encodeACLout(null, rawaclbdd, ports.size());
				for(String pport : ports)
				{
					if(outaclbddset.containsKey(pport))
					{
						outaclbddset.get(pport).add(aclbdd);
					}else
					{
						ArrayList<Integer> newset = new ArrayList<Integer>();
						newset.add(aclbdd);
						outaclbddset.put(pport, newset);
					}
				}
			}
		}

		inaclbdds = new HashMap<String, Integer>();
		outaclbdds = new HashMap<String, Integer>();
		for(String pport : inaclbddset.keySet())
		{
			ArrayList<Integer> bddset = inaclbddset.get(pport);
			int [] bdds = Utility.ArrayListToArray(bddset);
			//System.out.println(bdds.length);
			int andbdd = baw.AndInBatch(bdds);
			baw.DerefInBatch(bdds);
			inaclbdds.put(pport, andbdd);
		}
		for(String pport : outaclbddset.keySet())
		{
			ArrayList<Integer> bddset = outaclbddset.get(pport);
			int [] bdds = Utility.ArrayListToArray(bddset);
			int andbdd = baw.AndInBatch(bdds);
			baw.DerefInBatch(bdds);
			outaclbdds.put(pport, andbdd);
		}

		//System.out.println("in: " + inaclbdds);
		//System.out.println("out: " + outaclbdds);
	}

	public static void setBDDWrapper(BDDACLWrapper baw)
	{
		Device.baw = baw;
	}

	public HashSet<String> vlanToPhy(String vlanport)
	{
		return vlan_ports.get(vlanport);
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

		// in acl
		FWDAPSet fwtmp = new FWDAPSet(fwdaps);
		
		if(inaclaps.containsKey(port))
		{
			fwtmp.intersect(inaclaps.get(port));
		}

		//System.out.println(fwaps.keySet());

		Iterator iter = fwaps.entrySet().iterator();
		while(iter.hasNext())
		//for(String otherport : fwaps.keySet())
		{
			Map.Entry entry = (Map.Entry) iter.next();
			String otherport = (String) entry.getKey();
			//
			if(!otherport.equals(port))
			{
				FWDAPSet fwtmp1 = new FWDAPSet(fwtmp);
				fwtmp1.intersect((FWDAPSet) entry.getValue());
				if(!fwtmp1.isempty())
				{
					/*
					 * map vlan to physical port
					 */
					if(otherport.startsWith("vlan"))
					{
						HashSet<String> phyports = vlanToPhy(otherport);
						if(phyports == null)
						{

						}else
						{
							for(String pport:phyports)
							{
								FWDAPSet fwtmp2 = new FWDAPSet(fwtmp1);
								// cannot go back to the incoming port
								if(!pport.equals(port))
								{
									// out acl
									
									if(outaclaps.containsKey(pport))
									{
										fwtmp2.intersect(outaclaps.get(pport));
									}
									if(!fwtmp2.isempty())
									{
										fwded.put(pport, fwtmp2);
									}
								}
							}
						}
					}else{
						// out acl
						
						if(outaclaps.containsKey(otherport))
						{
							fwtmp1.intersect(outaclaps.get(otherport));
						}
						if(!fwtmp1.isempty())
						{
							fwded.put(otherport, fwtmp1);
						}
					}
				}
			}
		}

		return fwded;
	}

	/**
	 * forwarding, acls
	 * @param apc
	 */
	public void setaps(APComputer apc)
	{
		fwaps = new HashMap <String, FWDAPSet>();
		inaclaps = new HashMap<String, FWDAPSet>();
		outaclaps = new HashMap<String, FWDAPSet>();

		setaps_1(fwaps, fwbdds, apc);
		setaps_1(inaclaps, inaclbdds, apc);
		setaps_1(outaclaps, outaclbdds, apc);

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
	
	public void addSubnettoFWs()
	{
		for(String sname : subnets.keySet())
		{
			for(Subnet ones : subnets.get(sname))
			{
				fws.add(ones.convertoFW());
			}
		}
	}

	public void computeFWBDDs()
	{
		this.fwbdds = Device.baw.getfwdbdds(fws);
		//System.out.println(fwbdds.size());
		//for(String iname : fwbdds.keySet())
		//{
		//	System.out.println(iname + ": " + fwbdds.get(iname));
		//}
	}

	public void addACL(String name, LinkedList<ACLRule> acl)
	{
		aclmap.put(name, acl);
	}
	public void addFW(ForwardingRule fw)
	{
		fws.add(fw);
	}
	public void addVlanPorts(String vlan, HashSet<String> ports)
	{
		vlan_ports.put(vlan, ports);
	}
	public void addACLUse(ACLUse oneuse)
	{
		acluses.add(oneuse);
	}
	public void addSubnet(Subnet sub)
	{
		if(subnets.keySet().contains(sub.getname()))
		{
			subnets.get(sub.getname()).add(sub);
		}else
		{
			ArrayList<Subnet> subs = new ArrayList<Subnet>();
			subs.add(sub);
			subnets.put(sub.getname(), subs);
		}
	}

}
