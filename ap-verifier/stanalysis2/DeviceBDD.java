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

package stanalysis2;

import java.util.*;

import common.*;
import jdd.bdd.BDD;

public class DeviceBDD {
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
	HashMap<String, ACLAPSet> inaclaps;
	HashMap<String, ACLAPSet> outaclaps;
	
	public HashMap<String, HashSet<String>> get_vlan_mapping()
	{
		return vlan_ports;
	}
	
	public String get_name()
	{
		return this.name;
	}
	
	public HashMap<String, Integer> get_fwbdds_map()
	{
		return fwbdds;
	}
	
	public HashMap<String, FWDAPSet> get_fwaps_map()
	{
		return fwaps;
	}

	public void show_acls()
	{
		for (String name : aclmap.keySet())
		{
			if(aclmap.get(name).size() >= 40)
			{
				System.out.println("name:" + name);
				System.out.println(aclmap.get(name).size());
			}
		}
	}
	
	public int num_acl_rules_used()
	{
		int rule_count = 0;
		for (ACLUse one_use : acluses)
		{
			if(aclmap.containsKey(one_use.getnumber()))
			{
				rule_count = rule_count + aclmap.get(one_use.getnumber()).size();
			}
		}
		return rule_count;
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
	
	public void show_acl_bddsize()
	{
		for (String name : rawacl.keySet())
		{
			System.out.println(aclmap.get(name).size() + " " + baw.getNodeSize(rawacl.get(name)));
		}
	}

	public DeviceBDD(String dname)
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
		DeviceBDD.baw = baw;
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
	 * mapped VLan port may overlap with physical port...
	 */
	public HashMap <String, Integer> FowrdAction(String port, int apt)
	{
		HashMap <String, Integer> fwded = new HashMap<String, Integer>();
		
		BDD thebdd = baw.getBDD();

		// in acl
		int aptmp = apt;
		thebdd.ref(aptmp);
		
		if(inaclbdds.containsKey(port))
		{
			aptmp = thebdd.andTo(aptmp, inaclbdds.get(port));
		}

		//System.out.println(fwaps.keySet());

		Iterator iter = fwbdds.entrySet().iterator();
		while(iter.hasNext())
		//for(String otherport : fwaps.keySet())
		{
			Map.Entry entry = (Map.Entry) iter.next();
			String otherport = (String) entry.getKey();
			//
			if(!otherport.equals(port))
			{
				int aptmp1 = thebdd.ref(thebdd.and(aptmp, (Integer)entry.getValue()));
			
				
				if(aptmp1 != BDDACLWrapper.BDDFalse)
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
								// cannot go back to the incoming port
								if(!pport.equals(port))
								{
									// out acl
									int aptmp2 = thebdd.ref(aptmp1);
									if(outaclbdds.containsKey(pport))
									{
										aptmp2 = thebdd.andTo(aptmp2, outaclbdds.get(pport));
									}
									if(aptmp2 != BDDACLWrapper.BDDFalse)
									{
										fwded.put(pport, aptmp2);
									}
								}
							}
						}
					}else{
						// out acl
						if(outaclbdds.containsKey(otherport))
						{
							aptmp1 = thebdd.andTo(aptmp1, outaclbdds.get(otherport));
						}
						if(aptmp1 != BDDACLWrapper.BDDFalse)
						{
							fwded.put(otherport, aptmp1);
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
	public void setaps(APComputer apc1, APComputer apc2)
	{
		fwaps = new HashMap <String, FWDAPSet>();
		inaclaps = new HashMap<String, ACLAPSet>();
		outaclaps = new HashMap<String, ACLAPSet>();

		setaps_1(fwaps, fwbdds, apc1);
		setaps_2(inaclaps, inaclbdds, apc2);
		setaps_2(outaclaps, outaclbdds, apc2);

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
	
	private void setaps_2(HashMap<String, ACLAPSet> filteraps, 
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
				ACLAPSet aaps = new ACLAPSet(rawset);
				filteraps.put(portname, aaps);
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
		this.fwbdds = DeviceBDD.baw.getfwdbdds_sorted_no_store(fws);
		
		//this.fwbdds = DeviceAPT.baw.getfwdbdds(fws);
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

