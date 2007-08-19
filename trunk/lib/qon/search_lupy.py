"""
$Id: search_lupy.py,v 1.5 2005/10/03 04:36:24 alex Exp $

Implements Lupy as the search engine.
"""
from qon.search import SearchEngine, SearchResult

# imports to use lupy
from lupy.index.indexwriter import IndexWriter
from lupy.document import Document
from lupy.document import Field
from lupy.search import indexsearcher # for open
from lupy.index.term import Term
from lupy.indexer import Index

class SearchLupy(SearchEngine):
    
    def __init__(self, lupy_index_dir="/www/var/qon_lupy"):
        SearchEngine.__init__(self)
        self._lupy_index_dir = lupy_index_dir
        self._lupy_queue = []        

    def search(self, results, user, path, query, sort, start, end):
        """
        Perform a search in the 'text' field of each searchable item.

        If the search string is enclosed in double quotes, a phrase
        search will be run; otherwise, the search will be for
        documents containing all words specified.

        This lupy implementation ignores the sort parameter, and
        always sorts by relevance.
        """
        index = Index(self._lupy_index_dir, False)    
        hits = index.findInField(text=query)
        numhits = len(hits)

        # lupy is totally brain-dead, as it return the hits in reverse order
        #  (least relevant first, so we have to retrieve *all* the hits
        #   and work our way backwards)
        # also, hits.doc() has an obvious < vs. <= error that makes
        #  hits.doc() return a index out of range error, so i just call
        #  hits.getMoreDocs() to get every hit
        hits.getMoreDocs(numhits)

        # let's go through each hit in reverse order and assemble our
        #  list of search results.
        skipped = 0
        numhits_accessible = 0       
        for x in range(numhits-1, -1, -1):       
            d = hits.doc(x)

            if not self._can_read(d, user, path):
                continue                 

            # we got a good one, so tally it up            
            numhits_accessible += 1            

            # create a SearchResult object and append it to the end
            if skipped < start-1:
                skipped += 1
            else:
                if len(results) < (end - start + 1):                
                    sr = SearchResult(d, hits.score(x))              
                    results.append(sr)      

        return numhits_accessible        

    def _queue_document(self, fields, existing):
        qd = (fields, existing)
        self._lupy_queue.append(qd)  

    def commit_documents(self):
        # for lupy, put everyting in a single index because lupy
        # doesn't support multiple index searching
        writer = IndexWriter(self._lupy_index_dir, False)
        
        while len(self._lupy_queue) > 0:
            qd = self._lupy_queue.pop(0)
            fields = qd[0]
            existing = qd[1]

            """ add a document with the given fields to the index.
            If it's a document that already exists, delete it first, using the url as the key.
            """        
            if existing:
                # commit anything that's already been added by closing the writer
                writer.close()

                _delete_document(self._get_field_value(fields, 'url'))                

                # reopen writer
                writer = IndexWriter(self._lupy_index_dir, False)            

            # create a lupy document consisting of the fields
            d = Document()
            for x in fields:
                # converting to unicode keeps lupy happy, but then when we get the previews back
                #  we get an error when printing, so let's just punt and remove all bad characters
                # value = self._convert_text_from_iso8559_to_unicode(str(x[1]))
                value = self._remove_bad_characters(x[1])
               
                f = Field(str(x[0]), value, x[2], x[3], x[4])
                d.add(f)

            try:
                writer.addDocument(d)
            except:
                print "Lupy: could not add document: %s" % (self._get_field_value(fields, 'text')) 
                
        writer.close()               

    def _reset_index(self):
        index = IndexWriter(self._lupy_index_dir, True)

    def _optimize_index(self):
        index = IndexWriter(self._lupy_index_dir, False)
        index.optimize()
        index.close()

    def _delete_document(self, url):
        urlterm = Term('url', url)
        ir = indexsearcher.open(self._lupy_index_dir)
        num_deleted = ir.deleteTerm(urlterm)
        assert(num_deleted <= 1)
        ir.close()        

    # necessary for lupy which won't handle characters above 127 unless they are in unicode
    def _convert_text_from_iso8559_to_unicode(self, isostring):
        u = unicode(isostring, "ISO-8859-1")
        return u

