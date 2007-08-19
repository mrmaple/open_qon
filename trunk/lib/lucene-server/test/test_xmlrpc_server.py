import SimpleXMLRPCServer

class LuceneHandler:
    def __init__(self):
        self.lucene = self
    
    def queue_document(self, fields, existing, key, keyValue, boost):
        return True

    def commit_documents(self):
        return True

    def optimize_index(self):
        return True

    def reset_index(self):
        return True

    def delete_document(self, key, keyValue):
        return True

    def search(self, query, field, sortField, sortReverse, start, end):
        vHits = []
        return vHits

if __name__=='__main__':
    server = SimpleXMLRPCServer.SimpleXMLRPCServer(("localhost", 3888))
    server.register_instance(LuceneHandler())
    server.serve_forever()
    
