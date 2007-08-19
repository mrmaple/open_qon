#!/usr/bin/env python
"""
$Id: bulk_join_groups.py,v 1.1 2004/11/15 05:57:54 alex Exp $
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, get_database, close_database, \
    get_session_manager, get_group_database, transaction_commit
from qon import api
from qon.user import NotEnoughPrivileges

def join(group_db, child, parent):
    try:
        child_group = group_db[child]
    except KeyError:
        print '\nGroup "%s" not found' % (child)
        return

    try:
        parent_group = group_db[parent]
    except KeyError:
        print '\nGroup "%s" not found' % (parent)
        return

    print '\nJoining child "%s" to parent "%s"' % (child_group.display_name(), parent_group.display_name())

    # don't do anything if relationship already exists
    # if child_group.is_member_of_group(parent_group):
    if parent_group in group_db.member_groups(child_group):
        print ' Already joined.'
        return

    # try joining without joining the owner first
    try:
        api.group_join(parent_group, child_group)
        print ' Group succesfully joined.'
    except NotEnoughPrivileges:
        # ok, none of the owners of the child is a member of the parent,
        #  so let's join the first owner of the child group to the parent
        creator = child_group.owners[0]
        try:
            api.group_join(parent_group, creator)
            print ' Joined user "%s" to "%s"' % (creator.display_name(), parent_group.display_name())
            api.group_join(parent_group, child_group)
            print ' Group succesfully joined.'
        except NotEnoughPrivileges:
            print ' Failed because could not join user "%s" to "%s"' % (creator.display_name(), parent_group.display_name())
            return
            
    transaction_commit()          
    
    
if __name__ == "__main__":
    open_database()
    group_db = get_group_database()

    # do it
    join(group_db, 'federation', 'community-general')
    join(group_db, 'mini-action', 'community-general')
    join(group_db, 'on', 'community-general')
    join(group_db, 'reflections', 'community-general')
    join(group_db, 'resources', 'community-general')
    join(group_db, 'constitution', 'community-general')
    join(group_db, 'welcome', 'community-general')

    join(group_db, 'activestories', 'general-other')
    join(group_db, 'scouts', 'general-other')
    join(group_db, 'bookclub', 'general-other')
    join(group_db, 'buddies', 'general-other')
    join(group_db, 'campfire', 'general-other')
    join(group_db, 'food', 'general-other')
    join(group_db, 'funstuff', 'general-other')
    join(group_db, 'genealogy', 'general-other')
    join(group_db, 'goodapples', 'general-other')
    join(group_db, 'greatnews', 'general-other')
    join(group_db, 'safety', 'general-other')
    join(group_db, 'humor', 'general-other')
    join(group_db, 'inspirational_photos', 'general-other')
    join(group_db, 'jobs', 'general-other')
    join(group_db, 'success', 'general-other')
    join(group_db, 'partygroupies', 'general-other')
    join(group_db, 'poetry', 'general-other')
    join(group_db, 'whatworriesyou', 'general-other')
    join(group_db, 'inspire', 'general-other')
    join(group_db, 'thankfest', 'general-other')
    join(group_db, 'thoughts', 'general-other')
    join(group_db, 'travel', 'general-other')
    join(group_db, 'veggieexperiences', 'general-other')

    join(group_db, 'americandreaminc', 'issues-business')
    join(group_db, 'bizplanbuzz', 'issues-business')
    join(group_db, 'microus', 'issues-business')
    join(group_db, 'habit', 'issues-business')

    join(group_db, 'buddies_youth', 'issues-cyf')
    join(group_db, 'hearts', 'issues-cyf')
    join(group_db, 'teens', 'issues-cyf')
    join(group_db, 'ytfg', 'issues-cyf')

    join(group_db, 'education', 'issues-education')

    join(group_db, 'biofuels', 'issues-env')
    join(group_db, 'peacetrek', 'issues-env')
    join(group_db, 'sustainable_living', 'issues-env')
    join(group_db, 'worldheritage', 'issues-env')

    join(group_db, 'relationships', 'issues-general')
    join(group_db, 'psc', 'issues-general')
    join(group_db, 'culture', 'issues-general')
    join(group_db, 'economics', 'issues-general')
    join(group_db, 'empower', 'issues-general')
    join(group_db, 'ent', 'issues-general')
    join(group_db, 'solutionsecology', 'issues-general')
    join(group_db, 'patch', 'issues-general')
    join(group_db, 'philanthropy', 'issues-general')
    join(group_db, 'podis', 'issues-general')
    join(group_db, 'media', 'issues-general')
    join(group_db, 'ideas', 'issues-general')
    join(group_db, 'we', 'issues-general')
    join(group_db, 'liveonwhat', 'issues-general')
    join(group_db, 'windmills', 'issues-general')

    join(group_db, 'december1st', 'issues-health')
    join(group_db, 'drugs', 'issues-health')
    join(group_db, 'epihealth', 'issues-health')
    join(group_db, 'juvenilementalhealthcourtproject', 'issues-health')
    join(group_db, 'sleep', 'issues-health')
    
    join(group_db, 'progressive_values', 'issues-pol')
    join(group_db, 'political_moderation', 'issues-pol')
    join(group_db, 'justdemocracy', 'issues-pol')
    join(group_db, 'revisioningjustice', 'issues-pol')
    join(group_db, 'election', 'issues-pol')

    join(group_db, 'radio-africa', 'regional')
    join(group_db, 'sudancrisis', 'regional')
    join(group_db, 'haiti', 'regional')
    join(group_db, 'idaho', 'regional')
    join(group_db, 'nonam', 'regional')
    join(group_db, 'eurodream', 'regional')

    join(group_db, 'tincup', 'issues-soc')
    join(group_db, 'action', 'issues-soc')
    join(group_db, 'actnow', 'issues-soc')
    join(group_db, 'buddies_socialjustice', 'issues-soc')
    join(group_db, 'deathpenalty', 'issues-soc')
    join(group_db, 'jac', 'issues-soc')
    join(group_db, 'currencies', 'issues-soc')

    join(group_db, 'para', 'issues-tech')
    join(group_db, 'artfuture', 'issues-tech')
    join(group_db, 'buddies_tech', 'issues-tech')
    join(group_db, 'bios', 'issues-tech')
    join(group_db, 'cm_testing', 'issues-tech')
    join(group_db, 'workspot', 'issues-tech')
    join(group_db, 'compumentor', 'issues-tech')
    join(group_db, 'dlas', 'issues-tech')
    join(group_db, 'enumino', 'issues-tech')
    join(group_db, 'equiforum', 'issues-tech')
    join(group_db, 'games', 'issues-tech')
    join(group_db, 'topicmaps', 'issues-tech')
    join(group_db, 'allmath', 'issues-tech')
    join(group_db, 'networkcentricadvocacy', 'issues-tech')
    join(group_db, 'netchange', 'issues-tech')
    join(group_db, 'open-source', 'issues-tech')
    join(group_db, 'peace', 'issues-tech')
    join(group_db, 'blogalization', 'issues-tech')
    join(group_db, 'utility', 'issues-tech')
    join(group_db, 'web', 'issues-tech')

    join(group_db, 'givingspace', 'social')
    join(group_db, 'pcmerits', 'social')
    join(group_db, 'newsocialenterprises', 'social')
    join(group_db, 'gcc', 'social')
    join(group_db, 'uplift', 'social')

    # done
    print '\n'
    close_database()
