#!/usr/bin/env python
"""
$Id: test_http_loadtesting.py,v 1.14 2004/11/21 15:48:16 alex Exp $

Use http spidering techniques to load test qon.

Note: 09/29/04: Sign In is currently broken, so only anon users can be tested right now.
"""

from mechanize import Browser
from datetime import datetime, timedelta
import random                               # for randint
import urllib2                              # for HTTPError
import sys                                  # for exc_info
import urlparse                             # for urlparse
from threading import Thread
import ClientCookie                         # for OpenDirector in TimedBrowser
from ClientForm import ControlNotFoundError
# import psyco                                # for full()

def get_ms(td):
    """ Convert a timedelta to ms """
    return (td.days*86400 + td.seconds)*1000 + td.microseconds/1000

class TimedBrowser(Browser):
    """
    This class merely overrides the _open() function so that it records
    the latency of the last call made using this Browser.  Otherwise,
    trying to record the latency externally would also include the
    time it takes to parse the page, which is not fair to the site
    being tested.
    """

    def __init__(self, default_encoding="latin-1"):
        Browser.__init__(self)
        self.last_call_latency = 0
        Browser.set_debug_responses(self, True)
        Browser.set_debug_redirects(self, True)

    def _open(self, url, data=None, update_history=True):
        """ This is copied verbatim from Browser._open, except for the addition of
        the two timing lines around ClientCookie.OpenDirector.open() """
        try:
            url.get_full_url
        except AttributeError:
            # string URL -- convert to absolute URL if required
            scheme, netloc = urlparse.urlparse(url)[:2]
            if not scheme:
                # relative URL
                assert not netloc, "malformed URL"
                if self.response is None:
                    raise BrowserStateError(
                        "can't fetch relative URL: not viewing any document")
                url = urlparse.urljoin(self.response.geturl(), url)

        if self.request is not None:
            self._history.append((self.request, self.response))
        self.response = None
        # we want self.request to be assigned even if OpenerDirector.open fails
        self.request = self._request(url, data)
        self._previous_scheme = self.request.get_type()

        s_time = datetime.utcnow()                                      # Alex added
        self.response = ClientCookie.OpenerDirector.open(
            self, self.request, data)
        self.last_call_latency = get_ms(datetime.utcnow() - s_time)     # Alex added
        
        if not hasattr(self.response, "seek"):
            self.response = response_seek_wrapper(self.response)
        self._parse_html(self.response)

        return self.response    

class QonSingleSpider(Thread):
    
    def __init__(self, domain, starting_path, user, number_of_hits, verbose_output=False):
        Thread.__init__(self)
        self.domain = domain                    # e.g. "www.ginx.com:8156"
        self.starting_path = starting_path      # e.g. "/home/"
        self.user = user                        # e.g. ('Jim', 'jim@maplesong.com', 'jimc')
        self.number_of_hits = number_of_hits
        self.verbose_output = verbose_output
        self.b = TimedBrowser()
        self.latency_sum = 0                    # for calculating average latency
        self.errors = []                        # for keeping track of all the errors
        self.get_or_post = ""                    # for keeping track if the last call was a get or post

        # stats
        self.num_discussion_topics_created = 0
        self.num_comments_on_topics_made = 0
        self.num_wiki_pages_created = 0
        self.num_wiki_pages_edited = 0
        self.num_comments_on_wiki_pages_made = 0
        self.num_messages_sent = 0

        # if you want to harcode a list of urls to cycle throughh
        #  (rather than following random links), put them here
        self.urls = []

        """
        self.urls.append("/user/u163773627/")
        self.urls.append("/user/u387024026/")
        self.urls.append("/home/")            
#       self.urls.append("/user/new")
#       self.urls.append("/user/jimc/")            
#        self.urls.append("/group/community-general/news/25/")
#        self.urls.append("/group/issues-soc/news/11/")
        self.urls.append("/group/issues-tech/")
#       self.urls.append("/user/stats")
#       self.urls.append("/group/community-general/")
#       self.urls.append("/group/")
        self.xxx = 0
	"""

    def run(self):
        for x in range(1, self.number_of_hits+1):

            # do the hit
            self.do_next_hit()
            self.latency_sum += self.b.last_call_latency

            if self.verbose_output:
                print "-----------------------------------------------------------------------------------------------------------------" 

            if self.b.response is not None:
                if self.b.viewing_html():
                    title = self.b.title()
                else:
                    title = "[Non HTML Page]"
                relative_url = urlparse.urlparse(self.b.geturl())[2]
                alertstring = ""
                if self.b.last_call_latency > 1000:
                    alertstring = "SLOW"
                print "%s: %s %s %s (%s ms) %s" % (self.user[0].ljust(10), self.get_or_post, relative_url.ljust(50), title.ljust(45), self.b.last_call_latency, alertstring)

            self.b.last_call_latency = -1

        print "%s: DONE Avg Latency ==> %s ms" % (self.user[0], self.latency_sum / self.number_of_hits)                

    # if we're on a signin page, sign in
    def _sign_in(self, id):

        self.b.select_form(nr=1)                # select the second form (first one is search)
        try:
            self.b['email'] = self.user[1]
            self.b['password'] = self.user[2]
            self.b.submit(name="submit-login")
            print "%s:   Attempting signin with %s" % (id, self.user[1])
            self.get_or_post = "POST"
            return True
        except ControlNotFoundError:
            return False

    # if we're on a new discussion topic page, then post a new topic
    def _new_discussion_topic(self, id):
        self.b.select_form(nr=1)                # select the second form (first one is search)
        try:
            self.b['title'] = "Topic created by http load tester"
            self.b['intro'] = "The quick brown fox jumped over the lazy dog. "*10
            self.b.submit(name="submit-newitem")
            if self.verbose_output:
                print "%s:   Posting new discussion topic" % id
            self.num_discussion_topics_created += 1
            self.get_or_post = "POST"            
            return True
        except ControlNotFoundError:
            return False

    # if we're on a discussion page, then possibly post a comment and leave feedback
    def _comment_on_discussion_topic(self, id):

        # leave a comment only 33% of the time
        if random.randint(0,2) != 0:
            return False
 
        self.b.select_form(nr=1)                # select the second form (first one is search)       

        try:
            self.b['main'] = "I love this topic and I love to load test. "*3
            self.b['karma-item'] = ["do not leave feedback"]
            self.b['karma-author'] = ["do not leave feedback"]
            r = random.randint(0,100)
            if r > 95:
                self.b['karma-item'] = ["positive"]
                self.b['karma-author'] = ["positive"]
            if r < 2:
                self.b['karma-item'] = ["negative"]
                self.b['karma-author'] = ["negative"]

            self.b.submit(name="submit-newcomment")
            if self.verbose_output:
                print "%s:   Commenting on discussion topic" % id
            self.num_comments_on_topics_made += 1
            self.get_or_post = "POST"            
            return True
        except ControlNotFoundError:            
            return False

    # if we're on a new wiki page form, then make a new wiki page
    def _new_wiki_page(self, id):
        self.b.select_form(nr=1)                # select the second form (first one is search)
        
        try:
            r = random.randint(1, 100)
            self.b['__name'] = ("LoadTestingWikiPage%s" % r)
            self.b.submit(name="submit-newpage")
            if self.verbose_output:
                print "%s:   Creating new wiki page" % id
            self.num_wiki_pages_created += 1

            # immediately go to edit page or else the page doesn't really get created
            self.b.open(self.b.geturl() + "edit")

            self.get_or_post = "POST"
            
            return True
        except ControlNotFoundError:            
            return False

    # if we're on an edit wiki page form, then make an edit
    def _edit_wiki_page(self, id): 
        self.b.select_form(nr=1)                # select the second form (first one is search)

        try:
            self.b['__raw'] = self.b['__raw'] + "Load tester adding to wiki page. "*2
            self.b.submit(name="submit-edit")
            if self.verbose_output:
                print "%s:   Editing wiki page" % id
            self.num_wiki_pages_edited += 1
            self.get_or_post = "POST"            
            return True
        except ControlNotFoundError:
            return False

    # if we're on a wiki page, then possibly post a comment and leave positive feedback
    def _comment_on_wiki_page(self, id):

        # leave a comment only 5% of the time
        if random.randint(0,20) != 0:
            return False
        
        self.b.select_form(nr=1)                # select the second form (first one is search)

        try:
            self.b['main'] = "I love this wiki page and I love to load test. "*3
            self.b['karma-item'] = ["do not leave feedback"]
            r = random.randint(0,100)
            if r > 95:
                self.b['karma-item'] = ["positive"]
            if r < 2:
                self.b['karma-item'] = ["negative"]

            self.b.submit(name="submit-newcomment")
            if self.verbose_output:
                print "%s:   Commenting on wiki page" % id
            self.num_comments_on_wiki_pages_made += 1
            self.get_or_post = "POST"            
            return True
        except ControlNotFoundError:
            return False

    # if we're on a page to send a mesaage to a user, send a message
    def _send_message_to_user(self, id):
        self.b.select_form(nr=1)                # select the second form (first one is search)
        try:
            self.b['subject'] = "Message generated by http load testing tool."
            self.b['text'] = "I am sending you this message because I think you're cool. "*3
            self.b.submit(name="submit-newmsg")
            if self.verbose_output:
                print "%s:   Sending message" % id
            self.num_messages_sent += 1
            self.get_or_post = "POST"            
            return True
        except ControlNotFoundError:
            return False



    def do_next_hit(self):
        """
        Follow a random link using b
        """
        id = self.user[0]
        r = self.b.response
        self.get_or_post = "GET"

        # for possible error printing 
        if r:
            current_relative_url = urlparse.urlparse(self.b.geturl())[2]
 
        try:        
            link = None

            # if we're not even viewing a page, then let's start us off by hitting the homepage    
            if not r:
                starting_url = "http://" + self.domain + self.starting_path       # e.g. 'http://127.0.0.1:8081/'
                if self.verbose_output:
                    print "%s:      Starting up at '%s'" % (id, starting_url)       
                self.b.open(starting_url)
                return

            # if the page we're viewing is not html (like a pdf or an image), then hit the "back" button
            if not self.b.viewing_html():
                if self.verbose_output:
                    print "%s:      Not an HTML page -- clicking back button" % id            
                self.b.back()
                self.do_next_hit()
                return

            # get some basic info about the current html page we're viewing
            num_forms = len(self.b.forms())
            num_links = len(self.b.links())
            if self.verbose_output:
                print "%s:      Found %s links and %s form(s)" % (id, num_links, num_forms)

            # if we aren't anon, and there is a form on the page (other than search),
            #  detect the kind of form it is and possibly submit the form
            if num_forms > 1 and self.user[1] is not None:
                
                # check for sign-in; if it's the sign-in page, then definitely sign in
                if self._sign_in(id):
                    return

                # check for new discussion topic posting form
                if self._new_discussion_topic(id):
                    return

                # check for form for making a comment to a discussion topic
                if self._comment_on_discussion_topic(id):
                    return

                # check for new wiki page form
                if self._new_wiki_page(id):
                    return

                # check for edit wiki page form
                if self._edit_wiki_page(id):
                    return

                # check for form for making a comment on a wiki page
                if self._comment_on_wiki_page(id):
                    return

                # check for form for sending a messsage to a user
                if self._send_message_to_user(id):
                    return

            # check for hardcoded urls
            if self.urls and len(self.urls)>0:
                # self.xxx = random.randint(0, len(urls))
                self.xxx += 1
                if self.xxx == len(self.urls):
                    self.xxx = 0
                lucky_url = "http://" + self.domain + self.urls[self.xxx]
                self.b.open(lucky_url)
                return

            # find a random link on the page.
            #  must be an href 
            #  must be in this domain (don't follow external links)
            #  can't be javascript
            #  don't go to corp site
            #  don't go to same url that we're on now
            #  try up to 10 times
            tries = 0
            while ((not link) or \
                   (link.attrs[0][0] != 'href') or \
                   (self.domain not in link.absolute_url) or \
                   ('javascript' in link.absolute_url) or \
                   (link.absolute_url == link.base_url) or \
                   (link.url == '/')) \
                   and \
                   tries < 10 and num_links != 0:                 
                link = self.b.links()[random.randint(0, num_links-1)]
                if self.verbose_output:
                    print "%s:      Considering link '%s' leading to '%s'" % (id, link.text, link.url)
                tries += 1
                # print "  testing link.absolute_url = " + link.absolute_url

            if tries < 10 and num_links != 0:
                if self.verbose_output:
                    print "%s:      Clicking on '%s' leading to '%s'" % (id, link.text, link.url)
                # print "  going link.absolute_url = " + link.absolute_url
                # print "base= " + link.base_url + "  abs= " + link.absolute_url
                                
            else:
                if self.verbose_output:
                    print "%s:      Couldn't find an href link -- clicking back button" % id               
                self.b.back()
                self.do_next_hit()
                return       

            # follow the chosen link
            self.b.follow_link(link)
            return
    
#       except urllib2.HTTPError:
        except:
            error_string = str(sys.exc_info()[1])
            if self.verbose_output:            
                print "%s:      Got %s  -- clicking back button" % (id, error_string)
            if "403" not in error_string :
                if link:
                    link_relative_url = urlparse.urlparse(link.absolute_url)[2]
                if link:
                    detailed_error_string = "ERROR %s from '%s' to '%s'" % (error_string, current_relative_url, link_relative_url)
                else:
                    detailed_error_string = "ERROR %s from' %s'" % (error_string, current_relative_url)
                print "%s:      %s" % (id, detailed_error_string)
                self.errors.append(detailed_error_string)
            self.b.back()
            self.do_next_hit()
            return

        # should never get here
        assert(False)


if __name__ == "__main__":

#   psyco.full()

#   _domain = "www-test.ned.com"
    _domain = "www.foofun.com:8081"
#   _domain = "www.ned.com"
#   _domain = "localhost:8081"
#   _domain = "www.yahoo.com"
    _starting_path = "/home/"
 #  _starting_path = "/group/help/"
    _number_of_total_hits = 20

    users = [
#       ('Alex', 'poon@stanfordalumni.org', 'monster123o'),
        ('Anon1', None, None),
        ]

    _number_of_hits_per_user = _number_of_total_hits / len(users)

    # create all the spiders
    spiders = []
    for x in users:
        s = QonSingleSpider(_domain, _starting_path, x, _number_of_hits_per_user, verbose_output=False)
        spiders.append(s)

    start_time = datetime.utcnow()    

    # run all the spiders
    for s in spiders:
        print "Starting spider for user %s" % s.user[0]
        s.start()

    # suspend the main thread until all the other threads are done
    for s in spiders:
        s.join()

    # calculate stats
    total_hits = _number_of_hits_per_user*len(spiders)
    
    # latency
    latency_sum = 0
    for s in spiders:
        latency_sum += s.latency_sum
    average_latency = latency_sum / total_hits

    # stats
    num_discussion_topics_created = 0
    num_comments_on_topics_made = 0
    num_wiki_pages_created = 0
    num_wiki_pages_edited = 0
    num_comments_on_wiki_pages_made = 0
    num_messages_sent = 0
    for s in spiders:
        num_discussion_topics_created += s.num_discussion_topics_created 
        num_comments_on_topics_made += s.num_comments_on_topics_made
        num_wiki_pages_created += s.num_wiki_pages_created 
        num_wiki_pages_edited += s.num_wiki_pages_edited
        num_comments_on_wiki_pages_made += s.num_comments_on_wiki_pages_made
        num_messages_sent += s.num_messages_sent

    # print out all errors that we got
    e_num = 1
    print "-----------------------------------------------------------------------------------------------------------------"
    print "Errors:"
    for s in spiders:
        for e in s.errors:
            print "%s. %s" % (e_num, e)
            e_num += 1

    # page throughput
    elapsed_seconds = max((datetime.utcnow()-start_time).seconds, 1)
    num_per_seconds = float(total_hits) / float(elapsed_seconds)        


    print "-----------------------------------------------------------------------------------------------------------------"
    print "Finished."
    print "%s discussion topics created" % num_discussion_topics_created
    print "%s comments made on topics" % num_comments_on_topics_made
    print "%s new wiki pages created" % num_wiki_pages_created
    print "%s wiki pages edited" % num_wiki_pages_edited
    print "%s comments made on wiki pages" % num_comments_on_wiki_pages_made
    print "%s messages sent" % num_messages_sent
    print "%s pages in %s seconds ==> %s pages/sec" % (total_hits, elapsed_seconds, num_per_seconds)
    print "Average latency ==> %s ms" % average_latency

