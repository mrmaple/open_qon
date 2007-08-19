"""
$Id: search_lucene.py,v 1.33 2007/06/11 15:40:22 jimc Exp $

Implements Lucene over xmlrpc as the search engine.
"""
from qon.search import SearchEngine, SearchResult
from qon.karma import HasKarma
import qon.base

# imports to use lucene over xmlrpc
# we'll try to use py-xmlrpc (http://sourceforge.net/projects/py-xmlrpc/) first,
#  because it's a LOT faster than the the built-in python xmlrpc for FreeBSD.
#  (on Linux, the built-in one if fine).

_use_pyxmlrpc = True
try:
    from xmlrpc import client
    from xmlrpc import setLogLevel
    setLogLevel(0)  # supress debugging output to error.log
    import _xmlrpc
except ImportError:
    from xmlrpclib import Server
    _use_pyxmlrpc = False    

class SearchLucene(SearchEngine):

    def __init__(self, xmlrpc_server, fetch_increment=200):
        SearchEngine.__init__(self)

        if _use_pyxmlrpc:
            (host, port) = xmlrpc_server.split(':')
            self._server = client(host, int(port))
        else:
            self._server = Server("http://" + xmlrpc_server)
        self._fetch_increment = fetch_increment

    def search(self, results, user, types, query, sort, minKarma, minDate, group, start, end, min_breadth=0):
        """
        Perform a search in the 'text' field of each searchable item.

        Lucene's query parser allows boolean (AND,OR,NOT,+,-), wildcard (*),
        fuzzy (~), and phrase ("") matches. By default, terms use the AND operator.       
        """    

        # calculate how many results we need
        num_results_needed = end - start + 1

        # we'll try as many times as necessary to retrieve the number
        #  of matches requested, but usually we'll only need to try once
        num_to_retrieve = end + num_results_needed*2  # arbitrary padding
        my_results = []
        last_numhits = -1
        numhits_accessible = 0

        # pad karma with leading zeroes so sort works inside lucene
        if minKarma != 'any':
            minKarma = minKarma.zfill(6)

        numTries = 0
        maxTries = 2
            
        while len(my_results) < num_results_needed and numTries < maxTries:
            numTries += 1

            if sort == 'date' or sort == 'karma' or sort == 'end_date':
                reverse_sort = True
                if sort == 'end_date':
                    reverse_sort = False
                if _use_pyxmlrpc:
                    hits = self._server.execute('lucene.search', [query, types, str(minKarma), str(minDate), sort, _xmlrpc.boolean(reverse_sort), 1, num_to_retrieve])
                else:
                    hits = self._server.lucene.search(query, types, str(minKarma), str(minDate), sort, reverse_sort, 1, num_to_retrieve)              
            else:
                if _use_pyxmlrpc:
                    hits = self._server.execute('lucene.search', [query, types, str(minKarma), str(minDate), '', _xmlrpc.boolean(False), 1, num_to_retrieve])
                else:
                    hits = self._server.lucene.search(query, types, str(minKarma), str(minDate), '', False, 1, num_to_retrieve)
            numhits = len(hits) - 1 # -1 is to account for the last element, which is just the # of total hits

            # check to see if we didn't end up getting any more this round, and if not,
            #  let's not bother doing another round
            if numhits <= last_numhits:
                break
            last_numhits = numhits

            # last element is total # of hits
            num_total_hits = hits.pop()

            # let's go through each hit and assemble our
            #  list of search results.
            my_results = []
            skipped = 0
            numhits_accessible = 0         
            for d in hits:
                d['oid'] = self._decode_oid(d.get('oid'))
                
                try:
                    obj = qon.util.get_oid(d.get('oid'))
                    obj.can_read(user)       # every obj needs a can_read() method
                except:
                    continue

                if not self._can_read(d, user) or not self._matches_groups(d, user, group):
                    continue

                #if isinstance(d, HasKarma) and d.get_karma_breadth() < min_breadth:
                #obj = qon.util.get_oid(d.get('oid'))
                if isinstance(obj, HasKarma) and  obj.get_karma_breadth() < min_breadth:
                    continue

                # we got a good one, so tally it up            
                numhits_accessible += 1                

                # skip until we've reached our starting point
                if skipped < start-1:
                    skipped += 1
                else:
                    if len(my_results) < num_results_needed: 
                        # create a SearchResult object and append it to the end
                        sr = SearchResult(d, d.get('_score'))              
                        my_results.append(sr)

            # if we have to re-run the query, fetch more in the next iteration
            num_to_retrieve += self._fetch_increment
                        

        results.extend(my_results)

        # check to see if we "pinned the needle" which means there are probably
        #  more hits, but we stopped short because we got what we needed for this page
        if last_numhits == num_to_retrieve - self._fetch_increment:
            return num_total_hits * numhits_accessible / len(hits) # an estimate based on what % was filtered out
            
        return numhits_accessible             

    def _queue_document(self, fields, existing):

        if self.always_try_deleting_first:
            existing = True

        # modify a document's importance (boost) based on:
        # 1. karma (big boost)
        # 2. length of document (to compensate for lucene's algorithm, which tends to reward short documents)
        boost = 1.0;
        karma = self._get_field_value(fields, 'karma')
        text = self._get_field_value(fields, 'text')
        if karma:
            effective_karma = max(float(karma), -2) # to keep from boosting too low into oblivion
            boost += effective_karma / 6
        # boost *= pow(len(text), 0.5) / 50
        boost += pow(len(text), 0.2)

        # boost individual field names (query strings found in the title should be rewarded)
        type = self._get_field_value(fields, 'type')
        for x in fields:
            name = str(x[0])
            if name=='title':
                x.append(3.0)
            if name=='tags':
                x.append(3.0)
            elif name=='u_name' and type=='User':
                x.append(75.0)
            elif name=='u_name':
                x.append(3.0)                
            elif name=='g_name' and type=='Group':
                x.append(75.0)
            else:
                x.append(1.0)
            
        # convert all field names to strings and clean up field values
        if _use_pyxmlrpc:
            newfields = [(str(x[0]), self._remove_bad_characters(x[1]), _xmlrpc.boolean(x[2]), _xmlrpc.boolean(x[3]), _xmlrpc.boolean(x[4]), x[5]) for x in fields]
        else:
            newfields = [(str(x[0]), self._remove_bad_characters(x[1]), x[2], x[3], x[4], x[5]) for x in fields]            

        # send it to lucene!
        if _use_pyxmlrpc:
            ok = self._server.execute('lucene.queue_document',[_xmlrpc.boolean(self.async), newfields, _xmlrpc.boolean(existing), 'oid', self._get_field_value(fields, 'oid'), boost, _xmlrpc.boolean(self.commit_immediately)])
        else:
            ok = self._server.lucene.queue_document(self.async, newfields, existing, 'oid', self._get_field_value(fields, 'oid'), boost, self.commit_immediately)
        assert(ok)
          
    def commit_documents(self):
        if _use_pyxmlrpc:
            ok = self._server.execute('lucene.commit_documents', [_xmlrpc.boolean(self.async)])
        else:
            ok = self._server.lucene.commit_documents(self.async)
        assert(ok)

    def _reset_index(self):
        if _use_pyxmlrpc:        
            ok = self._server.execute('lucene.reset_index', [])
        else:
            ok = self._server.lucene.reset_index()
        assert(ok)

    def _optimize_index(self):
        if _use_pyxmlrpc:        
            ok = self._server.execute('lucene.optimize_index', [])
        else:
            ok = self._server.lucene.optimize_index()
        assert(ok)

    def _delete_document(self, oid):
        if _use_pyxmlrpc:        
            ok = self._server.execute('lucene.delete_document', ['oid', oid])
        else:
            ok = self._server.lucene.delete_document('oid', oid)
        assert(ok)
    
