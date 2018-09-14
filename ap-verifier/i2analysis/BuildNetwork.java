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

/**
 * Internet2 only has FIBs.
 *
 */

public class BuildNetwork {
	
	public static void main (String[] args) throws IOException
	{
		BDDACLWrapper baw = new BDDACLWrapper();
		Device.setBDDWrapper(baw);
		Device d = parseDevice("atla", "i2/atlaap");
		//System.out.println(d.subnets.size());
		d.computeFWBDDs();
	}

	public static Device parseDevice(String dname, String filenameparsed) throws IOException
	{
		Device d = new Device(dname);
		File inputFile = new File(filenameparsed);
		readParsed(d, inputFile);
		return d;
	}
	
	public static ForwardingRule assembleFW(String[] entries)
	{
		//use short name for physical port
		String portname = entries[3];
		
		if(entries[3].startsWith("vlan"))
		{
			portname = entries[3];
			System.out.println(portname);
		}else
		{
			//System.out.println(entries[3]);
			portname = entries[3].split("\\.")[0];
		}
		return new ForwardingRule(Long.parseLong(entries[1]), Integer.parseInt(entries[2]), portname);
	}
	

	
	public static void readParsed(Device d, File inputFile) throws IOException
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
			}
		}
	}
	
}
