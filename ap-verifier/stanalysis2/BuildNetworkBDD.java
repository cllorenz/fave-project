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

import java.io.*;
import java.util.*;

import common.*;
import common.ACLParser.ACLType;


public class BuildNetworkBDD {
	
	public static void main (String[] args) throws IOException
	{
		BDDACLWrapper baw = new BDDACLWrapper();
		DeviceBDD.setBDDWrapper(baw);
		DeviceBDD d = parseDeviceAPT("yoza_rtr", "stconfig/yoza_rtr_config.txt", "st/yoza_rtrap");
		d.computeACLBDDs();
		//System.out.println(d.subnets.size());
		//d.computeFWBDDs();
	}

	public static DeviceBDD parseDeviceAPT(String dname, String filename, String filenameparsed) throws IOException
	{
		DeviceBDD d = new DeviceBDD(dname);
		File inputFile = new File(filename);
		extractACLs(d, inputFile);
		inputFile = new File(filenameparsed);
		readParsed(d, inputFile);
		return d;
	}
	
	public static ForwardingRule assembleFW(String[] entries)
	{
		//use short name for physical port
		String portname;
		if(entries[3].startsWith("vlan"))
		{
			portname = entries[3];
		}else
		{
			//System.out.println(entries[3]);
			portname = entries[3].split("\\.")[0];
		}
		return new ForwardingRule(Long.parseLong(entries[1]), Integer.parseInt(entries[2]), portname);
	}
	
	public static Subnet assembleSubnet(String[] entries)
	{
		String name = entries[1];
		long ipaddr;
		int prefixlen;
		try{
			ipaddr = Long.parseLong(entries[2]);
			prefixlen = Integer.parseInt(entries[3]);
		}catch(Exception e)
		{
			//e.printStackTrace();
			return null;
		}
		return new Subnet(ipaddr, prefixlen, name);
	}
	
	public static void readParsed(DeviceBDD d, File inputFile) throws IOException
	{
		Scanner OneLine = null;
		try {
			OneLine = new Scanner (inputFile);
			OneLine.useDelimiter("\n");
			//scanner.useDelimiter(System.getProperty("line.separator"));
			// doesn't work for .conf files
		} catch (FileNotFoundException e) {
			System.out.println ("File not found!"); // for debugging
			System.exit (0); // Stop program if no file found
		}
		
		while(OneLine.hasNext())
		{
			String linestr = OneLine.next();
			String[] tokens = linestr.split(" ");
			if(tokens[0].equals( "fw"))
			{
				ForwardingRule onerule = assembleFW(tokens);
				d.addFW(onerule);
				//System.out.println("add: " + onerule);
			}else if(tokens[0].equals("vlanport"))
			{
				String vlanname = tokens[1];
				HashSet<String> ports = new HashSet<String>();
				for(int i = 2; i < tokens.length; i ++)
				{
					ports.add(tokens[i]);
				}
				d.addVlanPorts(vlanname, ports);
				//System.out.println("add: " + vlanname + " " + ports);
			}else if(tokens[0].equals("acl"))
			{
				for (int i = 0; i < (tokens.length - 2)/2; i ++)
				{
					d.addACLUse(new ACLUse(tokens[1], tokens[(i+1)*2], tokens[(i+1)*2+1]));
					//System.out.println(tokens[1] + " " + tokens[(i+1)*2] + " " + tokens[(i+1)*2+1]);
				}
			}else if(tokens[0].equals("subnet"))
			{
				Subnet sub = assembleSubnet(tokens);
				if(sub != null)
				{
					d.addSubnet(sub);
					//System.out.println(sub);
				}
			}
		}
	}
	
	// build aclmap in device d
	public  static void extractACLs(DeviceBDD d, File inputFile) throws IOException
	{

		/************************************************************************
		 * Set up a Scanner to read the file using tokens
		 ************************************************************************/
		Scanner OneLine = null;
		try {
			OneLine = new Scanner (inputFile);
			OneLine.useDelimiter("\n");
			//scanner.useDelimiter(System.getProperty("line.separator"));
			// doesn't work for .conf files
		} catch (FileNotFoundException e) {
			System.out.println ("File not found!"); // for debugging
			System.exit (0); // Stop program if no file found
		}

		/* Read line by line */
		while (OneLine.hasNext()) {
			/* Read token by token in each line */
			Scanner TokenInLine = new Scanner(OneLine.next());
			String keyword;
			if (TokenInLine.hasNext()) {
				keyword = TokenInLine.next();
				/**************************************************************
				 * This section handles ACL rules that start with "access-list"
				 ***************************************************************/
				if (keyword.equals("access-list")) {
					HandleAccessList(OneLine, TokenInLine, d);
				}
				/* handles acl rules that start with ip access-list extend/standard*/
				else if(keyword.equals("ip"))
				{
					keyword = TokenInLine.next();
					if(keyword.equals("access-list"))
					{
						HandleAccessListGrouped(OneLine, TokenInLine, d);
					}
				}
			}
		} // end of while (oneline.hasNext())
	}
	

	static void HandleAccessListGrouped(Scanner oneline, Scanner tokeninline, DeviceBDD d)throws IOException
	{
		ArrayList<String> argument = new ArrayList<String> ();
		ACLParser.GetArgument(tokeninline, argument);
		while(true){
			//"access-list" already removed		
			LinkedList<ACLRule> oneacl = new LinkedList<ACLRule>();
			ACLType thisType;
			if(argument.get(0).equals("extended"))
			{
				thisType = ACLType.extend;
			}else
			{
				thisType = ACLType.standard;
			}
			String thisNumber = argument.get(1);

			while(true){
				tokeninline = new Scanner(oneline.next());
				ACLParser.GetArgument(tokeninline, argument);
				if(argument.get(0).equals("ip"))
				{//a new ACL, need to add the old one 
					d.addACL(thisNumber, oneacl);
					argument.remove(0);// remove ip
					argument.remove(0);// remove access-list, so that it can restart
					//Parser.DebugInput(System.out, null, "Add:"+thisNumber);
					break;
				}
				if((!argument.get(0).equals("permit")) && (!argument.get(0).equals("deny")))
				{//this means the end of the ACL definition
					d.addACL(thisNumber, oneacl);
					//Parser.DebugInput(System.out, null, "Add:"+thisNumber);
					return;
				}
				ACLRule onerule = new ACLRule();
				onerule.accessList = "access-list";
				onerule.accessListNumber = thisNumber;
				ACLParser.CheckPermitDeny(onerule, argument);
				if(thisType == ACLType.extend)
				{
					ACLParser.HandleACLRuleExtend(onerule, argument);
				}else{
					ACLParser.HandleACLRuleStandard(onerule, argument);
				}
				oneacl.add(onerule);
			}
		}

	}

	static void HandleAccessList(Scanner oneline, Scanner tokeninline, DeviceBDD d) throws IOException
	{
		ArrayList<String> argument = new ArrayList<String>();
		/**set up argument, 'access-list' has already been parsed*/
		ACLParser.GetArgument(tokeninline, argument);

		// Test Function 1 : output argument array into a test file
		//DebugInput(System.out, argument, "access-list");

		int currentACLNum = -1;
		int preACLNum = -1;
		int[] aclNumbers = {preACLNum, currentACLNum};// pay attention to the order

		ACLRule onerule = null;
		LinkedList<ACLRule> oneacl = new LinkedList<ACLRule>();

		if(ACLParser.CheckValidACL(argument, aclNumbers))
		{
			onerule = new ACLRule();
			onerule.accessList = "access-list";

			preACLNum = aclNumbers[0];
			currentACLNum = aclNumbers[1];
			onerule.accessListNumber = Integer.toString(currentACLNum);
			//
			ACLParser.AddDynamic(onerule, argument);
			ACLParser.CheckPermitDeny(onerule, argument);

			if(ACLParser.CheckACLType(currentACLNum) == ACLType.standard)
			{
				ACLParser.HandleACLRuleStandard(onerule, argument);
			}else
			{
				ACLParser.HandleACLRuleExtend(onerule, argument);
			}
			oneacl.add(onerule);
		}


		while(oneline.hasNext())
		{
			String keyword = "";
			tokeninline = new Scanner(oneline.next());
			if(tokeninline.hasNext()){
				keyword = tokeninline.next();
			}else{
				// seems reach the end of file, finish parsing
				break;
			}
			if(keyword.equals("access-list"))
			{
				aclNumbers[0] = preACLNum; 
				aclNumbers[1] = currentACLNum;
				ACLParser.GetArgument(tokeninline, argument);

				if(ACLParser.CheckValidACL(argument, aclNumbers))
				{
					preACLNum = aclNumbers[0];
					currentACLNum = aclNumbers[1];
					if(preACLNum != currentACLNum)
					{
						// finish parsing an acl, add to the router
						d.addACL(Integer.toString(preACLNum), oneacl);

						//debug
						ArrayList<String> oneaclInfo = new ArrayList<String>();
						oneaclInfo.add(oneacl.get(0).accessListNumber);
						oneaclInfo.add(Integer.toString(oneacl.size()));
						//Parser.DebugInput(System.out, oneaclInfo, "added access-list");

						// get a new one to store
						oneacl = new LinkedList<ACLRule>();
						preACLNum = currentACLNum;
					}

					onerule = new ACLRule();
					onerule.accessList = "access-list";

					onerule.accessListNumber = Integer.toString(currentACLNum);
					//
					ACLParser.AddDynamic(onerule, argument);
					ACLParser.CheckPermitDeny(onerule, argument);

					if(ACLParser.CheckACLType(currentACLNum) == ACLType.standard)
					{
						ACLParser.HandleACLRuleStandard(onerule, argument);
					}else
					{
						ACLParser.HandleACLRuleExtend(onerule, argument);
					}
					//debug
					//DebugTools.IntermediateACLRuleCheck(onerule, System.out);
					oneacl.add(onerule);
				}

			}else
			{// the acl part ends
				break;
			}
		}

		// need to add the last acl
		if(currentACLNum != -1)
		{
			//debug
			ArrayList<String> oneaclInfo = new ArrayList<String>();
			oneaclInfo.add(oneacl.get(0).accessListNumber);
			oneaclInfo.add(Integer.toString(oneacl.size()));
			//Parser.DebugInput(System.out, oneaclInfo, "added access-list");
			d.addACL(Integer.toString(currentACLNum), oneacl);
		}

	}
}

