/*
 * Server.java
 *
 * Created on June 17, 2004, 8:34 PM
 */

// $Id: Server.java,v 1.2 2004/06/22 22:36:06 pierre Exp $

import java.io.IOException;
import org.apache.xmlrpc.WebServer;
import org.apache.xmlrpc.XmlRpc;
import java.io.FileWriter;
import java.util.Date;
import java.io.File;      

/**
 *
 * @author  Alex
 */
public class Server {
    
    /** Creates a new instance of Server */
    public Server() {}
    
    /**
     * @param args the command line arguments
     */
    public static void main(String[] args) {
        // start up the server from the command line
        
        if (args.length < 3) {
            System.err.println("Usage: java Server [port] [indexFile] [logfiledir]");
            System.err.println(" E.g.: java Server 3888 /www/var/qon_lucene /www/log/qon/lucene");            
            System.exit(-1);
        }
        
        // Create the server, using xmlrpc's built-in mini webserver
        WebServer server = new WebServer(Integer.parseInt(args[0]));
        System.out.println("\n");
        System.out.println("Started Lucene XML-RPC Server.");
        
        // Open logfile and errorlogfile
        FileWriter logOut = null;
	FileWriter errorOut = null;
	String logoutfile = args[2] + "/output.log";
	String erroutfile = args[2] + "/error.log";
        try {
            File f;
            if (!(f = new File(args[2])).exists()) f.mkdir();
            logOut = new FileWriter(logoutfile, true);
            errorOut = new FileWriter(erroutfile, true);
        } catch (Exception e) {
            System.err.println("Could not open log files. Exiting.");            
            System.exit(-1);            
        }
        System.out.println("Log file => " + logoutfile);
	System.out.println("Error log file => " + erroutfile);

        // Register our handler classes
        server.addHandler("lucene", new LuceneHandler(args[1], logOut, errorOut)); 
	System.out.println("Lucene data directory => " + args[1]);
        
        // Start it up
        server.start();
        System.out.println("Now accepting requests on port " + args[0] + ". (Run stop-lucene.sh to stop).");

	// Create first entry in log for this run
        try { logOut.write("\n\n" + new Date().toString() + " - Starting up lucene server with index " + args[1] + " on port " + args[0]); logOut.flush(); } catch (IOException w) {}  
    }
    
}
