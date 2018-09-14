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

/**
 * Helper functions to parse port and protocol numbers in ACL rule
 * 
 * Some functions are taken from E. G. W. W. Wong. Validating Network Security
 * Policies Via Static Analysis of Router ACL Configuration (Thesis, Naval 
 * Postgraduate School, December 2006). https://calhoun.nps.edu/handle/10945/2426
 */
public class PortProtocolParser {

	public static void ParsePort (ACLRule aclRule, ArrayList<String> argument, String port) {
		// handles eq, gt, lt, range
		// to include handling for neq
		if (argument.get(0).equalsIgnoreCase("eq")) { // handles eq
			argument.remove(0);
			if (port.equals("source")) {
				aclRule.sourcePortLower = GetPortNumber (argument.get(0));
				aclRule.sourcePortUpper = aclRule.sourcePortLower;
				argument.remove(0);
			}
			else if (port.equals("destination")) {
				aclRule.destinationPortLower = GetPortNumber (argument.get(0));
				aclRule.destinationPortUpper = aclRule.destinationPortLower;
			}
		}
		else if (argument.get(0).equalsIgnoreCase("gt")) {
			argument.remove(0);
			if (port.equals("source")) {
				aclRule.sourcePortLower = GetPortNumber (argument.get(0));
				argument.remove(0);
			}
			else if (port.equals("destination"))
				aclRule.destinationPortLower = GetPortNumber (argument.get(0));
		}
		else if (argument.get(0).equalsIgnoreCase("lt")) {
			argument.remove(0);
			if (port.equals("source")) {
				aclRule.sourcePortUpper = GetPortNumber (argument.get(0));
				argument.remove(0);
			}
			else if (port.equals("destination"))
				aclRule.destinationPortUpper = GetPortNumber (argument.get(0));
		}
		else if (argument.get(0).equalsIgnoreCase("range")) {
			argument.remove(0);
			if (port.equals("source")) {
				aclRule.sourcePortLower = GetPortNumber (argument.get(0));
				argument.remove(0);
				aclRule.sourcePortUpper = GetPortNumber (argument.get(0));
				argument.remove(0);
			}
			else if (port.equals("destination")) {
				aclRule.destinationPortLower = GetPortNumber (argument.get(0));
				argument.remove(0);
				aclRule.destinationPortUpper = GetPortNumber (argument.get(0));
			}
		}
	}

	static String GetPortNumber (String port) {
		String portNumber;
		// Note switch statement does not work with strings
		if (port.equalsIgnoreCase("tcpmux")) portNumber = "1";
		else if (port.equalsIgnoreCase("ftp-data")) portNumber = "20";
		else if (port.equalsIgnoreCase("ftp")) portNumber = "21";
		else if (port.equalsIgnoreCase("ssh")) portNumber = "22";
		else if (port.equalsIgnoreCase("telnet")) portNumber = "23";
		else if (port.equalsIgnoreCase("smtp")) portNumber= "25";
		else if (port.equalsIgnoreCase("dsp")) portNumber= "33";
		else if (port.equalsIgnoreCase("time")) portNumber= "37";
		else if (port.equalsIgnoreCase("rap")) portNumber= "38";
		else if (port.equalsIgnoreCase("rlp")) portNumber= "39";
		else if (port.equalsIgnoreCase("name")) portNumber= "42";
		else if (port.equalsIgnoreCase("nameserver")) portNumber= "42";
		else if (port.equalsIgnoreCase("nicname")) portNumber= "43";
		else if (port.equalsIgnoreCase("dns")) portNumber = "53";
		else if (port.equalsIgnoreCase("domain")) portNumber = "53";
		else if (port.equalsIgnoreCase("bootps")) portNumber = "67";
		else if (port.equalsIgnoreCase("bootpc")) portNumber = "68";
		else if (port.equalsIgnoreCase("tftp")) portNumber = "69";
		else if (port.equalsIgnoreCase("gopher")) portNumber = "70";
		else if (port.equalsIgnoreCase("finger")) portNumber = "79";
		else if (port.equalsIgnoreCase("http")) portNumber = "80";
		else if (port.equalsIgnoreCase("www")) portNumber = "80";
		else if (port.equalsIgnoreCase("kerberos")) portNumber = "88";
		else if (port.equalsIgnoreCase("pop2")) portNumber = "109";
		else if (port.equalsIgnoreCase("pop3")) portNumber = "110";
		else if (port.equalsIgnoreCase("sunrpc")) portNumber = "111";
		else if (port.equalsIgnoreCase("ident")) portNumber = "113";
		else if (port.equalsIgnoreCase("auth")) portNumber = "113";
		else if (port.equalsIgnoreCase("sftp")) portNumber = "115";
		else if (port.equalsIgnoreCase("nntp")) portNumber = "119";
		else if (port.equalsIgnoreCase("ntp")) portNumber = "123";
		else if (port.equalsIgnoreCase("netbios-ns")) portNumber = "137";
		else if (port.toLowerCase().startsWith("netbios-dg")) portNumber = "138";
		else if (port.toLowerCase().startsWith("netbios-ss")) portNumber = "139";
		else if (port.equalsIgnoreCase("sqlsrv")) portNumber = "156";
		else if (port.equalsIgnoreCase("snmp")) portNumber = "161";
		else if (port.equalsIgnoreCase("snmptrap")) portNumber = "162";
		else if (port.equalsIgnoreCase("bgp")) portNumber = "179";
		else if (port.equalsIgnoreCase("exec")) portNumber = "512";
		else if (port.equalsIgnoreCase("shell")) portNumber = "514";
		else if (port.equalsIgnoreCase("isakmp")) portNumber = "500";
		else if (port.equalsIgnoreCase("biff")) portNumber = "512";
		else if (port.equalsIgnoreCase("lpd")) portNumber = "515";
		else if (port.equalsIgnoreCase("cmd")) portNumber = "514";
		else if (port.equalsIgnoreCase("syslog")) portNumber = "514";
		else if (port.equalsIgnoreCase("whois")) portNumber = "43";
		else if (port.equals("lLth9012b03GJ")) portNumber = "390"; //this is ad hoc
		else portNumber = port;
		return portNumber;
	}

	public static String GetProtocolNumber (String protocol) {
		String protocolNumber;
		if(protocol.equalsIgnoreCase("icmp")) protocolNumber = "1" ;
		else if(protocol.equalsIgnoreCase("igmp")) protocolNumber = "2" ;
		//else if(protocol.equalsIgnoreCase("ip")) protocolNumber = "4" ;
		else if(protocol.equalsIgnoreCase("ip")) protocolNumber = "256" ;
		// special case to indicate all protocols. No actual protocol number 256.
		else if(protocol.equalsIgnoreCase("tcp")) protocolNumber = "6" ;
		else if(protocol.equalsIgnoreCase("egp")) protocolNumber = "8" ;
		else if(protocol.equalsIgnoreCase("igp")) protocolNumber = "9" ;
		else if(protocol.equalsIgnoreCase("udp")) protocolNumber = "17" ;
		else if(protocol.equalsIgnoreCase("rdp")) protocolNumber = "27" ;
		else if(protocol.equalsIgnoreCase("ipv6")) protocolNumber = "41" ;
		else if(protocol.equalsIgnoreCase("rsvp")) protocolNumber = "46" ;
		else if(protocol.equalsIgnoreCase("eigrp")) protocolNumber = "88" ;
		else if(protocol.equalsIgnoreCase("l2tp")) protocolNumber = "115" ;
		else if(protocol.equalsIgnoreCase("esp")) protocolNumber = "50";
		else if(protocol.equalsIgnoreCase("ahp")) protocolNumber = "51";
		else if(protocol.equalsIgnoreCase("gre")) protocolNumber = "47";
		else if(protocol.equalsIgnoreCase("ospf")) protocolNumber = "89";
		else {
			System.out.println("Unknown Protocol: " + protocol + "----------------------------");
			protocolNumber = protocol ;
		}
		return protocolNumber;
	}

}
