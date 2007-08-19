/*
 * BasicServer.java
 *
 */

// $Id: BasicServer.java,v 1.1 2004/07/30 05:28:42 alex Exp $

import java.io.IOException;
import org.apache.xmlrpc.WebServer;
import org.apache.xmlrpc.XmlRpc;

/**
 *
 * @author  Alex
 */


public class BasicServer {
    
    /** Creates a new instance of Server */
    public BasicServer() {}
    
    /**
     * @param args the command line arguments
     */
    public static void main(String[] args) {
        // start up the server from the command line
        
        if (args.length < 1) {
            System.err.println("Usage: java BasicServer [port]");
            System.err.println(" E.g.: java BasicServer 3999");            
            System.exit(-1);
        }
        
        // Create the server, using xmlrpc's built-in mini webserver
        WebServer server = new WebServer(Integer.parseInt(args[0]));
        System.out.println("\n");
        System.out.println("Started BasicServer.");
        
        // Register our handler classes
        server.addHandler("test", new TestHandler()); 
        
        // Start it up
        server.start();
        System.out.println("Now accepting requests on port " + args[0] + ".");

    }
    
}
