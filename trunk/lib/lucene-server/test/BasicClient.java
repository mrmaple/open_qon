/*
 * BasicClient.java
 *
 */

// $Id: BasicClient.java,v 1.3 2004/07/30 21:24:41 alex Exp $

import java.io.IOException;
import org.apache.xmlrpc.XmlRpcClient;
import org.apache.xmlrpc.XmlRpc;
import java.util.Vector;

/**
 *
 * @author  Alex
 */



public class BasicClient {
    
    /** Creates a new instance of Server */
    public BasicClient() {}
    
    /**
     * @param args the command line arguments
     */
    public static void main(String[] args) {

	try {
	    XmlRpcClient xmlrpc = new XmlRpcClient ("http://localhost:4000");
	    Vector params = new Vector();
	    params.addElement (new Integer(12));
	    Integer result;
	    
	    for (int i=0; i<10000; i++) {
		result = (Integer) xmlrpc.execute ("test.go", params);
//		System.out.println("result " + result.toString());
	    }

	} catch (Exception e) {
	    System.out.println(e.toString());
	}

    }
    
}
