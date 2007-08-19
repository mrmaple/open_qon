#!/usr/bin/env python

import xmlrpclib


_secure_host = 'http://localhost:8081/home/xmlrpc'
_host = 'http://localhost:8081/home/xmlrpc'
_user = 'jimc'
_pass = ''

def main():
    global _secure_host, _host, _user, _pass
    global secure, server

    secure = xmlrpclib.ServerProxy(_secure_host)
    server = xmlrpclib.ServerProxy(_host)

    lb = secure.login(_user, _pass)

    atom_id = server.user_atom_id(lb, 'jimc')

    user_content = server.user_content(lb, atom_id, ['all'], 0)
    user_data = server.user_data(lb, atom_id, ['all'])

    friends = server.user_info(lb, user_data['posffrom'])

    print user_content
    print user_data
    print friends

    print server.item_data(lb, 'tag:foo:/group/community-general/news/606/', ['feedback', 'text', 'html'])
    

if __name__ == '__main__':
    main()

