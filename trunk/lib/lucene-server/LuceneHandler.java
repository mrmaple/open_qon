/*
 *LuceneHandler.java
 *
 * Created on June 17, 2004, 8:42 PM
 */

// $Id: LuceneHandler.java,v 1.18 2007/02/18 15:04:39 jimc Exp $

import java.io.FileWriter;
import java.util.Date;
import java.io.IOException;
import org.apache.lucene.index.IndexWriter;
import org.apache.lucene.analysis.standard.StandardAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.index.IndexReader;
import org.apache.lucene.index.Term;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.queryParser.QueryParser;
import org.apache.lucene.search.Query;
import org.apache.lucene.search.BooleanQuery;
import org.apache.lucene.search.Hits;
import org.apache.lucene.search.Sort;
import org.apache.lucene.search.RangeQuery;
import org.apache.lucene.search.BooleanClause;
//import org.apache.lucene.search.BooleanClause.Occur;
import org.apache.lucene.search.Filter;
// import org.apache.lucene.search.RangeFilter;
import java.io.File;
import java.util.Vector;
import java.util.Hashtable;
import java.util.Enumeration;

/**
 *
 * @author  Alex
 */
public class LuceneHandler {

    private String mIndexFile = null;       // e.g. "/www/var/qon_lucene"
    private Vector mQueuedDocuments = null; // it's important that vector operations are thread-safe
    private static int MAX_Q_SIZE = 5000;   // we don't want the Q to get too big before we commit (we might run out of memory)
    private FileWriter mLogOut = null;
    private FileWriter mErrorOut = null;

    /** Creates a new instance of LuceneHandler */
    public LuceneHandler(String indexFile, FileWriter logOut, FileWriter errorOut) {
        mIndexFile = indexFile;
        mQueuedDocuments = new Vector();
        mLogOut = logOut;
        mErrorOut = errorOut;
    }

    private IndexWriter _open_index() {
        // Load index (and create if it doesn't yet exist)
        try {
            File f;
            boolean create;
            if ((f = new File(mIndexFile)).exists() && f.isDirectory()) {
                create = false;
            } else {
                create = true;
                try { mLogOut.write("\n" + new Date().toString() + " - Creating new index " + mIndexFile); mLogOut.flush(); } catch (IOException w) {}
            }
            return new IndexWriter(mIndexFile, new StandardAnalyzer(), create);
        } catch (Exception e) {
            // critical error, so exit
            try { mErrorOut.write("\n" + new Date().toString() + " - Could not open index " + mIndexFile); mErrorOut.flush(); } catch (IOException w) {}
            System.exit(-1);
        }
        return null;
    }

    private void _close_index(IndexWriter writer) {
        try {
            if (writer != null) writer.close();
        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Could not close index " + mIndexFile); mErrorOut.flush(); } catch (IOException w) {}
        }
    }

    // Queues up document to the index.
    // Queueing makes batch indexing *much* faster because batch prcoesses don't call commit_documents()
    //  until after having queued up a lot of documents.  This way, we don't open and close the
    //  index for every document.
    // Real-time indexing, however, should just pass true for commit_immediately.
    // -------------
    // Parameters
    // -------------
    // async, if true, will return true immediately and create a new thread to process the request
    // fields is a vector of vectors, where the inside vectors are of the format:
    //  (name, value, isStored, isIndexed, isTokenized)
    // existing tells us if we should try to delete the document before adding it
    // key tells us the name of the field that is used for deletion (e.g., "url")
    // keyValue tells us value of the key field in case existing==true
    // boost specifies how much extra relevance to give to this document
    // commit_immediately, when set to true, will commit this document immediately
    public Boolean queue_document(boolean async, Vector fields, boolean existing, String key, String keyValue, double boost, boolean commit_immediately) {
	
	if (!async) {
	    // do it immediately and block until it's done
	    return _queue_document(fields, existing, key, keyValue, boost, commit_immediately);
	} else {
	    // create a new thread to do the queuing, and return immediately
	    class HelperThread extends Thread {
		Vector mFields;
		boolean mExisting;
		String mKey;
		String mKeyValue;
		double mBoost;
		boolean mCommitImmediately;
		HelperThread(Vector fields, boolean existing, String key, String keyValue, double boost, boolean commit_immediately) {
		    mFields = fields;
		    mExisting = existing;
		    mKey = key;
		    mKeyValue = keyValue;
		    mBoost = boost;
		    mCommitImmediately = commit_immediately;
		}
		public void run() { _queue_document(mFields, mExisting, mKey, mKeyValue, mBoost, mCommitImmediately); }
	    }
	    HelperThread t = new HelperThread(fields, existing, key, keyValue, boost, commit_immediately);
	    t.start();
	    return new Boolean(true);
	}
    }

    // 10/19/2004 -- added synchronized keyword because the new async feature was causing document dupes when 
    // users made a comment on a blogitem and gave a positive feedback 
    private synchronized Boolean _queue_document(Vector fields, boolean existing, String key, String keyValue, double boost, boolean commit_immediately) {
        try {
            // if the document existed in the index already, try deleting it first
	    //  note that doing the delete here vs at the commit stage opens up the very slight possiblity
	    //  that a document could end up the index more than once via a race condition.  however,
	    //  it would be corrected the next time the document is re-indexed.
            if (existing) {
                Boolean b = delete_document(key, keyValue);
                if (b.booleanValue()==false) {
                    try { mErrorOut.write("\n" + new Date().toString() + " - Error deleting queued document " + keyValue); mErrorOut.flush(); } catch (IOException w) {}
                    return new Boolean(false);
                }
            }

            Document d = new Document();
            int num_fields = fields.size();
            for (int i = 0; i < num_fields; i++) {
                Vector x = (Vector)fields.get(i);
                Field f = new Field((String)x.get(0), (String)x.get(1), ((Boolean)x.get(2)).booleanValue(), ((Boolean)x.get(3)).booleanValue(), ((Boolean)x.get(4)).booleanValue());
		double fieldboost = ((Double)x.get(5)).doubleValue();
                // try { mLogOut.write("\n" + new Date().toString() + " - Field: " + (String)x.get(0) + " Value: " + (String)x.get(1) + " Boost: " + (float)fieldboost); mLogOut.flush(); } catch (IOException w) {}
                d.add(f);
		f.setBoost((float)fieldboost);
            }
            if (boost != 0.0) d.setBoost((float)boost);
            mQueuedDocuments.add(d);
            try { mLogOut.write("\n" + new Date().toString() + " - Queued document " + keyValue); mLogOut.flush(); } catch (IOException w) {}
        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Error queueing document " + keyValue); mErrorOut.flush(); } catch (IOException w) {}
            return new Boolean(false);
        }

        // go ahead and commit if asked, or if the queued up batch is getting big
        if ((commit_immediately) || (mQueuedDocuments.size() > MAX_Q_SIZE)) {
            _commit_documents();
        }

        return new Boolean(true);

        }

    // We use synchronized here so that multiple threads won't commit, optimize or reset the index
    //  at the same time.
    // ------------
    // Parameters
    // ------------
    // async, if true, will return true immediately and create a new thread to process the request
    public  Boolean commit_documents(boolean async) {
        if (!async) {
            // do it immediately and block until it's done
            return _commit_documents();
        } else {
            // create a new thread to do the committing, and return immediately
            class HelperThread extends Thread {
                HelperThread() {}
                public void run() { _commit_documents(); }
            }
            HelperThread t = new HelperThread();
            t.start();
            return new Boolean(true);
        }

    }

    private synchronized Boolean _commit_documents() {
        IndexWriter writer = null;
	int num_committed = 0;
        try {
            writer =_open_index();
            writer.mergeFactor = 10;          // 10 is default anyway (lower means optimize() will be called more often)
	    writer.maxFieldLength = 30000;  // max # of terms that will be indexed per field (default is 10000)
	    // note that the while loop is writen so that document that are queue'd up during
	    //  the loop by another thread will be committed too.  and yes, vector operations are thread-safe.
            while (mQueuedDocuments.size() > 0) {
                Document d = (Document)mQueuedDocuments.remove(0);
                writer.addDocument(d);
		num_committed++;
            }
        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Error committing documents"); mErrorOut.flush(); } catch (IOException w) {}
            _close_index(writer);
            return new Boolean(false);
        }
        _close_index(writer);
        try { mLogOut.write("\n" + new Date().toString() + " - Committed " + num_committed + " documents"); mLogOut.flush(); } catch (IOException w) {}
	return new Boolean(true); //  2006-03-20: decided that optimizing after every document was too performance-intensive, and should be ok now that what's new uses filters
        // return optimize_index();  //  added 08-11-2004: found that if we don't optimize enough, what's new will eventually complain and return 0 items
    }

    // Manually optimize the index.
    // The remote client would call this after a long batch index.
    // async, if true, will return true immediately and create a new thread to process the request
    public synchronized Boolean optimize_index() {
        IndexWriter writer = null;
        try {
            writer =_open_index();
            writer.optimize();
        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Could not optimize index " + mIndexFile); mErrorOut.flush(); } catch (IOException w) {}
            _close_index(writer);
            return new Boolean(false);
        }
        try { mLogOut.write("\n" + new Date().toString() + " - Optimized index " + mIndexFile); mLogOut.flush(); } catch (IOException w) {}
        _close_index(writer);
        return new Boolean(true);
    }

    // Erase the index and re-open it.
    // The remote client would call this in preparation for a batch index.
    public synchronized Boolean reset_index() {
        mQueuedDocuments.removeAllElements();  // if we already have some documents Q'd, get rid of them, or else we might end up with dupes

        IndexWriter writer = null;
        try {
            writer = new IndexWriter(mIndexFile, new StandardAnalyzer(), true);
        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Could not open index " + mIndexFile); mErrorOut.flush(); } catch (IOException w) {}
            _close_index(writer);
            return new Boolean(false);
        }
        try { mLogOut.write("\n" + new Date().toString() + " - Reset index " + mIndexFile); mLogOut.flush(); } catch (IOException w) {}
        _close_index(writer);
        return new Boolean(true);
    }

    public synchronized Boolean delete_document(String key, String keyValue) {
        IndexReader ir = null;
        try {
            ir = IndexReader.open(mIndexFile);
            Term t = new Term(key, keyValue);
            int num_deleted = ir.delete(t);
            try { mLogOut.write("\n" + new Date().toString() + " - Deleted " + num_deleted + " instances of document " + keyValue); mLogOut.flush(); } catch (IOException w) {}
        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Error deleting document " + keyValue); mErrorOut.flush(); } catch (IOException w) {}
            try {
                if (ir != null) ir.close();
                return new Boolean(false);
            } catch (Exception e2) {
                try { mErrorOut.write("\n" + new Date().toString() + " - Error closing IndexReader after error deleting document " + keyValue); mErrorOut.flush(); } catch (IOException w) {}
                return new Boolean(false);
            }
        }
        try {
            if (ir != null) ir.close();
            return new Boolean(true);
        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Error closing IndexReader after deleting document " + keyValue); mErrorOut.flush(); } catch (IOException w) {}
            return new Boolean(false);
        }
    }

    // Do a search.
    // Return a Vector of hits, where each hit is a Hashtable of name/value pairs
    // A special name, "_score" contains the score of the hit
    // We absolutely do *not* want to use synchronized here, because this is the
    //  routine that will be called the most.
    // By the way, the reason we don't try to store a reusable QueryParser as a class
    //  field is that it's not thread-safe.
    // And the reason we don't try to store a reusable IndexSearcher is that we
    //  want every search to come back with the newest results.
    // Alex 2005-01-15: Made it so that the very last element in the Vector
    //  is an Integer representing the total # of hits
    // Alex 2006-02-14: added minKarma and minDate (set to "any" to ignore)
    // Comments as of 02/16/2006:
    //   query: keywords required to be in text ("" allowed)
    //   types: vector of allowed types ("User", "Group", "Usernews", "UsernewsComment", "Discussion", "DiscussionComment", "Wikipage", Poll) -- if vector is empty, allow ALL types
    //   minKarma: "any" or karma score that all hits should be above (e.g. "000008")
    //   minDate: "any" or number of seconds since June 1, 1970 GMT that document must have been updated greater than
    //   sortField: what field to sort by (e.g. "karma" or "date") -- if "" then sort by relevance
    //   sortReverse: whether to sort descending or not
    //   start/end: for pagination
    public Vector search(String query, Vector types, String minKarma, String minDate, String sortField, boolean sortReverse, int start, int end) {
        Vector vHits = new Vector();
        IndexSearcher searcher = null;
        Hits hits = null;
        try {
            searcher = new IndexSearcher(mIndexFile);
            BooleanQuery finalQuery = new BooleanQuery();
	    finalQuery.setMaxClauseCount(1024);  // default is 1024

	    if (query.length() > 0) {
		// make sure ALL keywords are in the text body
      		QueryParser qp_text  = new QueryParser("text", new StandardAnalyzer());
		qp_text.setOperator(QueryParser.DEFAULT_OPERATOR_AND);
		finalQuery.add(qp_text.parse(query), true, false);

		// add an OR clause for the user name (soley for boosting purposes)
		QueryParser qp_u_name  = new QueryParser("u_name", new StandardAnalyzer());
		qp_u_name.setOperator(QueryParser.DEFAULT_OPERATOR_OR);
		finalQuery.add(qp_u_name.parse(query), false, false);

		// add an OR clause for the group name (soley for boosting purposes)
		QueryParser qp_g_name  = new QueryParser("g_name", new StandardAnalyzer());
		qp_g_name.setOperator(QueryParser.DEFAULT_OPERATOR_AND);
		finalQuery.add(qp_g_name.parse(query), false, false);

		// add an OR clause for the title (soley for boosting purposes)
		QueryParser qp_title  = new QueryParser("title", new StandardAnalyzer());
		qp_title.setOperator(QueryParser.DEFAULT_OPERATOR_OR);
		finalQuery.add(qp_title.parse(query), false, false);
	    }

            // constrain by type if there are any type constraints (otherwise, allow ALL types)
            int num_types = types.size();
	    if (num_types > 0) {
		String allowedTypes = "";
		for (int i = 0; i < num_types; i++) {
		    String t = (String)types.get(i);
		    allowedTypes += t + " ";
		}
		allowedTypes = allowedTypes.trim();
		QueryParser qp = new QueryParser("type", new StandardAnalyzer());
		qp.setOperator(QueryParser.DEFAULT_OPERATOR_OR);
		finalQuery.add(qp.parse(allowedTypes), true, false);
	    }

	    Filter[] chain = null;
	    boolean useKarmaFilter = !minKarma.equals("any");
	    boolean useDateFilter = !minDate.equals("any");
	    if ((useKarmaFilter) && (useDateFilter)) chain = new Filter[2];
	    else if ((!useKarmaFilter) && (!useDateFilter)) chain = null;
	    else chain = new Filter[1];
	    
	    // possibly constrain by minKarma
	    int x = 0;
	    if (useKarmaFilter) {
		chain[x++] = RangeFilter.More("karma", minKarma);
	    }

	    // possibly constrain by minDate
	    if (useDateFilter) {
		chain[x++] = RangeFilter.More("date", minDate);
	    }

	    // do the search w/ or w/o any filters
	    if (chain != null) {
		ChainedFilter chainedfilter = new ChainedFilter(chain, ChainedFilter.AND);
		if (sortField.length() == 0) {
		    hits = searcher.search(finalQuery, chainedfilter);
		} else {
		    Sort s = new Sort(sortField, sortReverse);
		    hits = searcher.search(finalQuery, chainedfilter, s);
		}
	    } else {
		if (sortField.length() == 0) {
		    hits = searcher.search(finalQuery);
		} else {
		    Sort s = new Sort(sortField, sortReverse);
		    hits = searcher.search(finalQuery, s);
		}
	    }

            int num_hits = hits.length();

            // Convert the Document's (inside hits) to a vector of Hashtables (vHits)
            for (int i=start-1; (i<num_hits) && (i<end); i++) {
                Document d = hits.doc(i);
                Hashtable hashDoc = new Hashtable();
                Field f;
                for (Enumeration fields = d.fields(); fields.hasMoreElements(); ) {
                    f=(Field)fields.nextElement();
                    hashDoc.put(f.name(), f.stringValue());
                }
		double score = (double)(hits.score(i));
		// don't send anything less than .001 because py-xmlrpc barfs on E-4
		if (score < .001) score = .001;
		hashDoc.put("_score", new Double(score));
                vHits.add(hashDoc);
            }

	    // added 2005-01-15
	    vHits.add(new Integer(num_hits));

            try { mLogOut.write("\n" + new Date().toString() + " - Performed query " + query + " and found " + num_hits + " hits (returning " + (vHits.size()-1) + ")"); mLogOut.flush(); } catch (IOException w) {}

            try {
                searcher.close();
            } catch (Exception e) {
                try { mErrorOut.write("\n" + new Date().toString() + " - Could not close searcher for " + query + " on index " + mIndexFile + ". Got " + e.toString()); mErrorOut.flush(); } catch (IOException w) {}
            }

        } catch (Exception e) {
            try { mErrorOut.write("\n" + new Date().toString() + " - Could not perform query " + query + " on index " + mIndexFile + ". Got " + e.toString()); mErrorOut.flush(); } catch (IOException w) {}
            try {
                searcher.close();
            } catch (Exception e2) {
                try { mErrorOut.write("\n" + new Date().toString() + " - Could not close searcher for " + query + " on index " + mIndexFile + ". Got " + e.toString()); mErrorOut.flush(); } catch (IOException w) {}
            }
	}
        return vHits;

    }

}
