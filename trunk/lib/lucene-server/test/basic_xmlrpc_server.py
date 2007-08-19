import SimpleXMLRPCServer

class TestFunctions:
    def __init__(self):
        pass
    
    def go(self, x):
        return x*2;

if __name__=='__main__':
    server = SimpleXMLRPCServer.SimpleXMLRPCServer(("localhost", 3999))
    server.register_instance(TestFunctions())
    server.serve_forever()
    
