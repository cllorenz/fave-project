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

import java.util.*;

/**
 * Helper functions to process ACL rules.
 * 
 * Some functions are taken from E. G. W. W. Wong. Validating Network Security
 * Policies Via Static Analysis of Router ACL Configuration (Thesis, Naval 
 * Postgraduate School, December 2006). https://calhoun.nps.edu/handle/10945/2426
 */
public class ACLParser {

	public static enum ACLType{
		standard, extend;
	}

	public static void GetArgument(Scanner tokeninline, ArrayList<String> argument)
	{
		argument.clear();
		while(tokeninline.hasNext())
		{
			argument.add(tokeninline.next());
		}
	}

	/**
	 * aclNumbers[0] -- previous acl number
	 * aclNumbers[1] -- current acl number
	 * return true the acl is valid
	 * return false the acl is invalid
	 * */
	public static boolean CheckValidACL(ArrayList<String> argument, int[] aclNumbers)
	{
		try{
			if(aclNumbers[0] == -1)
			{
				aclNumbers[0] = Integer.valueOf(argument.get(0));
				aclNumbers[1] = aclNumbers[0];
				argument.remove(0);
			}else
			{
				aclNumbers[1] = Integer.valueOf(argument.get(0));
				argument.remove(0);
			}
		} catch(NumberFormatException e)
		{
			//the acl rule is not valid
			return false;
		}

		if(argument.get(0).equals("remark"))
		{
			return false;
		}else{
			return true;
		}
	}

	public static void AddDynamic(ACLRule onerule, ArrayList<String> argument)
	{
		if (argument.get(0).equals ("dynamic")) {
			onerule.dynamic="dynamic";
			argument.remove(0);
			onerule.dynamicName=argument.get(0);
			argument.remove(0);
		}
	}

	public static void CheckPermitDeny(ACLRule onerule, ArrayList<String> argument)
	{
		if(argument.get(0).equals("permit"))
		{
			onerule.permitDeny = "permit";
		}else
		{
			onerule.permitDeny = "deny";
		}
		argument.remove(0); 
	}

	public static void HandleACLRuleStandard(ACLRule onerule, ArrayList<String> argument)
	{
		//acl number has been removed.
		// the first argument is the ip address
		if(argument.get(0).equals("host"))
		{
			argument.remove(0);
		}

		onerule.source = argument.get(0);
		argument.remove(0);
		if(!argument.isEmpty())
		{
			if(!argument.get(0).equals("log")){
				onerule.sourceWildcard = argument.get(0);
			}
		}

	}

	public static void HandleACLRuleExtend(ACLRule onerule, ArrayList<String> argument)
	{
		//first is the protocol
		onerule.protocolLower = PortProtocolParser.GetProtocolNumber(argument.get(0));
		if (onerule.protocolLower.equals("256")) {
			onerule.protocolLower = "0";
			onerule.protocolUpper = "255";
		}else {
			onerule.protocolUpper = onerule.protocolLower;
		}
		argument.remove(0);

		// then is the source field
		if (argument.get(0).equals("any")) {
			onerule.source = "any";
			argument.remove(0);
			PortProtocolParser.ParsePort (onerule, argument, "source");
		}
		else if (argument.get(0).equals("host")) {
			argument.remove(0);
			onerule.source = argument.get(0);
			argument.remove(0);
			PortProtocolParser.ParsePort (onerule, argument, "source");
		}
		else {// the last case uses wildcard
			onerule.source = argument.get(0);
			argument.remove(0);
			onerule.sourceWildcard = argument.get(0);
			argument.remove(0);
			PortProtocolParser.ParsePort (onerule, argument, "source");
		}

		//the last is the destination field
		/*** If the destination keyword is "any" ***/
		if (argument.get(0).equals("any")) {
			onerule.destination = "any";
			argument.remove(0);
			if (!argument.isEmpty()){
				PortProtocolParser.ParsePort (onerule, argument, "destination");
			}
		}
		else if (argument.get(0).equals("host")) {
			argument.remove(0);
			onerule.destination = argument.get(0);
			argument.remove(0);
			if (! argument.isEmpty()){
				PortProtocolParser.ParsePort (onerule, argument, "destination");
			}
		}
		else {
			onerule.destination = argument.get(0);
			argument.remove(0);
			onerule.destinationWildcard = argument.get(0);
			argument.remove(0);
			if (! argument.isEmpty()){
				PortProtocolParser.ParsePort (onerule, argument, "destination");
			}
		}
	}

	public static ACLType CheckACLType(int aclnum)
	{
		if (aclnum >=1 && aclnum <=99 )
			return ACLType.standard ;
		else if (aclnum >=100 && aclnum <=199 )
			return ACLType.extend;
		else if (aclnum >= 1300 && aclnum <=1999 )
			return ACLType.standard;
		else if (aclnum >=2000 && aclnum <=2699 )
			return ACLType.extend;
		//by default
		return ACLType.extend;
	}

}
