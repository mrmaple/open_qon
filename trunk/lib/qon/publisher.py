from dulcinea.ui.publisher import DulcineaPublisher
from datetime import datetime
from qon import local
import qon.log
from qon.base import get_database, get_user
import random

class QonPublisher(DulcineaPublisher):
    """Currently this subclass doesn't do anything.
    
    DulcineaPublisher.try_publish is the main publishing loop, and contains
    logic to handle/retry ZODB ConflictError exceptions.
    """
    def __init__ (self):
        DulcineaPublisher.__init__(self)

    def start_request (self, request):
        DulcineaPublisher.start_request(self, request)
        
        # look at request and set up appropriate i18n translator
        self._setup_gettext(request)
    
    def finish_failed_request (self, request):
        """Called when any exception other than a PublishError is raised."""
        import sys
        from ZEO.Exceptions import ClientDisconnected
        (exc_type, exc_value, tb) = sys.exc_info()
        if isinstance(exc_value, ClientDisconnected):
            return '''
                <html><body><p>Sorry, the database is currently undergoing maintenance.
                Please check back again in a few minutes.</p></body></html>
                '''
        return DulcineaPublisher.finish_failed_request(self, request)
        
    def finish_successful_request(self, request):
        """Commit any version upgrades that might have happened."""
        from base import commit_upgraded_versioneds
        
        commit_upgraded_versioneds()
        DulcineaPublisher.finish_successful_request(self, request)
    
    def _setup_gettext(self, request):
        accept_languages = request._parse_pref_header(request.environ.get("HTTP_ACCEPT_LANGUAGE", ""))

        byqual = []
        for l, q in accept_languages.items():
            byqual.append((q, l))
        byqual.sort()
        byqual.reverse()
        
        if not byqual:
            byqual = [(1.0, 'en')]
        
        # install the translator
        # can't install globally since we're running a single server which
        # serves requests from anywhere
        # so let's hook it up to the request object itself
        import gettext
        try:
            # locale library pukes on en-us, translate everything to en_us, for instance.
            t = gettext.translation('qon', '/www/locale',
                languages=[l.replace('-', '_') for q, l in byqual])
        except IOError:
            # print "ERROR: couldn't find translator: %s" % byqual
            pass
        else:
            request.gettext = t.gettext

    def process_request (self, request, env):
        from quixote.publish import Publisher      

        url = request.get_url()
        method = request.get_method()        
        
        try:
            has_profile_request = (request.environ['QUERY_STRING'].find('__profile') != -1)
        except:
            has_profile_request = False

        # if has_profile_request or (('/edit' in url) and (method=='POST')) or ('.xml' in url):
        # if has_profile_request or (('/edit' in url) and (method=='POST')):                    
        if has_profile_request:       
            import sys, os, hotshot, hotshot.stats
            import cStringIO
            
            file_name = os.tempnam('/var/tmp', 'scgi.prof.')
            
            prof = hotshot.Profile(file_name)
            result = prof.runcall(Publisher.process_request, self, request, env)
            prof.close()
            
            stats = hotshot.stats.load(file_name).strip_dirs().sort_stats("cumulative")
            os.unlink(file_name)
            
            stats_io = cStringIO.StringIO()
            save_stdout = sys.stdout
            sys.stdout = stats_io
            stats.print_stats(100)
            sys.stdout = save_stdout
            
            from qon.util import sendmail
            sendmail("Profile Output: %s %s" % (method, url), stats_io.getvalue(), ['jim@maplesong.com'])
            stats_io.close()
            
            
            return result

        else:
            # for recording cache activity            
            pre_accesses = get_database().storage._cache.fc._n_accesses
            pre_adds = get_database().storage._cache.fc._n_adds            
            pre_added_bytes = get_database().storage._cache.fc._n_added_bytes
            pre_evicts = get_database().storage._cache.fc._n_evicts
            pre_evicted_bytes = get_database().storage._cache.fc._n_evicted_bytes

            # for timing each request
            start = datetime.utcnow()

            # DO IT            
            result = Publisher.process_request(self, request, env)

            # get elapsed time            
            td = datetime.utcnow() - start
            time_in_ms = td.seconds*1000 + td.microseconds/1000

            # for recording basic cache activity
            total_added_bytes = get_database().storage._cache.fc._n_added_bytes
            total_evicted_bytes = get_database().storage._cache.fc._n_evicted_bytes
            accesses = get_database().storage._cache.fc._n_accesses - pre_accesses
            adds = get_database().storage._cache.fc._n_adds - pre_adds            
            added_bytes = total_added_bytes - pre_added_bytes
            evicts = get_database().storage._cache.fc._n_evicts - pre_evicts
            evicted_bytes = total_evicted_bytes - pre_evicted_bytes            

            # log slow requests to a file (and for now, any edits)
            # if (time_in_ms > local.LOG_TIMING_MIN_MS) or (('/edit' in url) and (method=='POST')) or (random.randint(0,99)==0):
            # if (time_in_ms > local.LOG_TIMING_MIN_MS) or (('/edit' in url) and (method=='POST')):
            if (time_in_ms > local.LOG_TIMING_MIN_MS):
                if local.CACHE_INSTRUMENTATION:
                    # report detailed cache stats
                    detailed_cache_stats = get_database().storage._cache.fc.get_formatted_cache_stats()
                    qon.log.timing_info('%s\t%s\t%d ms\t(%d ac; %d a, %d ab, %d tab; %d e, %d eb, %d teb\n%s' \
                                        % (method, url, time_in_ms, accesses, adds, added_bytes, total_added_bytes, evicts, evicted_bytes, total_evicted_bytes, detailed_cache_stats))
                else:
                    # just report basic cache stats
                    qon.log.timing_info('%s\t%s\t%d ms\t(%d ac; %d a, %d ab, %d tab; %d e, %d eb, %d teb)' \
                                        % (method, url, time_in_ms, accesses, adds, added_bytes, total_added_bytes, evicts, evicted_bytes, total_evicted_bytes))

            # record histogram of times for reporting on admin page
            record_time(url, get_user(), time_in_ms)
            
                    
        if local.CACHE_INSTRUMENTATION:
            # clear out lists to ready for next call
            detailed_cache_stats = get_database().storage._cache.fc.clear_oid_lists()
            
        return result



# for timing histogram -- key are timing thresholds, values are counts
overall_timing_histogram = {2:0, 5:0, 10:0, 20:0, 86400:0 }
logged_in_histogram = {2:0, 5:0, 10:0, 20:0, 86400:0 }
anonymous_histogram = {2:0, 5:0, 10:0, 20:0, 86400:0 }
xml_histogram = {2:0, 5:0, 10:0, 20:0, 86400:0 }
histogram_list = (overall_timing_histogram, logged_in_histogram, anonymous_histogram, xml_histogram)

def record_time(url, user, time_in_ms):
    """
    record time for each relevant list
    """
    xml = ".xml" in url
    for h in histogram_list:
        if (h is logged_in_histogram) and ((not user) or xml):
            continue
        if (h is anonymous_histogram) and (user or xml):
            continue
        if (h is xml_histogram) and (not xml):
            continue
        sorted_items = h.items()
        sorted_items.sort()    
        for k, v in sorted_items:    
            if time_in_ms <= k*1000:
                h[k] += 1
                break

def get_times():
    """
    returns a list of a list of (histogram name, category, # hits, % hits)
    """
    results_list = []
    for h in histogram_list:    
        sorted_items = h.items()
        sorted_items.sort()      
        histogram = []
        total_hits = 0
        for k, v in sorted_items:
            total_hits += v
        total_hits = total_hits or 1    # avoid division by 0          
        for k, v in sorted_items:
            histogram.append((k, v, str(float(v)/float(total_hits)*100) + "%"))
        results_list.append(histogram)
    return results_list
