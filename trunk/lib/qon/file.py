"""
$Id: file.py,v 1.19 2006/05/10 02:14:25 alex Exp $

NOTE: parts of this file's code comes from dulcinea
"""
import os, time, string
import shutil
from datetime import datetime
from dulcinea import site_util

from qon.base import QonPersistent
from qon.user_db import GenericDB
from persistent.list import PersistentList


ALLOWABLE_SPECIAL_CHARS = "-_.@"
_last_name = None


def path_check(path):
    """(path:string) -> string | None

    Return a lower-case and normalized version of the 'path' after
    checking for allowable characters.
    Return None if path has '..' or any special characters
    other than what's in string.lowercase, string.digits, and
    the ALLOWABLE_SPECIAL_CHARS string
    """
    if '..' in path:
        return None
    path = path.lower()
    for letter in path:
        if (letter != '/' and letter not in string.lowercase and
            letter not in string.digits and
            letter not in ALLOWABLE_SPECIAL_CHARS):
            return None
    return path

class StoredFile(QonPersistent):
    """A single file object.
    
    See dulcinea.stored_file.StoredFile for original source.
    """

    MIME_TYPES = [("image/gif", "GIF image"),
                  ("image/jpeg", "JPEG image"),
                  ("image/png", "PNG image"),
                  ("image/tiff", "TIFF image"),
                  ("image/x-ms-bmp", "BMP image"),
                  ("text/plain", "plain text"),
                  ("text/html", "HTML text"),
                  ("text/rtf", "richtext document"),
                  ("application/pdf", "PDF document"),
                  ("application/msword", "Word document"),
                  ("application/vnd.ms-powerpoint", "PowerPoint document"),
                  ("application/postscript", "PostScript file"),
                  ("application/octet-stream", "Binary data"),
                  ("application/x-gzip", "Compressed file"),
                  ("application/x-tar", "Uncompressed tar file"),
                  ("application/x-compressed", "Compressed tar file"),
                  ("application/x-zip-compressed", "Compressed ZIP file"),
                  ("application/x-zip", "Compressed ZIP file"),
                  ]
    
    
    def __init__(self, path, root_dir, source_path=None):
        """(path: str, root_dir : string, source_path : string)

        If 'source_path' exists, copy the file specified to the file-store
        location specified in 'path'.  'path' specifies a relative path, so
        the full path is root_dir + path.

        If 'path' contains directories, traverse into those directories
        creating them as needed. 'source_path' must be readable if specified.
        """
        self.description = None
        self.owner = None
        self.date = datetime.utcnow()

        # Check path for safety (no '..' components, that sort of thing)
        path = os.path.normpath(path)
        self.path = path_check(path)
        assert self.path, 'Bad name: %r' % path
        self.filename = os.path.basename(self.path)

        self.full_path = os.path.join(root_dir, self.path)
        assert not os.path.exists(self.full_path), (
            'path %r already exists' % self.full_path)

        if source_path:
            # Copy the file specified in source_path into the file-store
            f = open(source_path, mode='rb')
            f2 = self.open(mode='wb')
            shutil.copyfileobj(f, f2)
            f.close()
            f2.close()

        self.mime_type = self.guess_mime_type()
        
    def __repr__(self):
        return '<%s: path=%r>' % (self.__class__.__name__, self.path)

    def get_path(self):
        return self.path

    def get_mime_type(self):
        return self.mime_type

    def get_full_path(self):
        """() -> string
        """
        return self.full_path

    def guess_mime_type(self):
        # FIXME this is OS-dependant!
        #p = os.popen("file -b --mime '%s' 2>/dev/null" % self.get_full_path())
        p = os.popen("file -bi '%s' 2>/dev/null" % self.get_full_path())
        mime_type = p.read().strip()
        if ';' in mime_type:
            mime_type = mime_type.split(';')[0]
        status_ignore = p.close() # 'file' seems to always return error status 0!
        # only allow MIME types we know about
        for (type, description) in self.MIME_TYPES:
            if type == mime_type:
                break
        else:
            mime_type = "application/octet-stream"
        return mime_type

    def open(self, mode='rb'):
        """(mode:string) -> file
        Returns a Python file object opened for reading or writing,
        depending on the 'mode' parameter.  This can be used to read or
        update the file's content.
        """
        full_path = self.get_full_path()
        if 'w' in mode:
            dir = os.path.dirname(full_path)
            if not os.path.exists(dir):
                os.makedirs(dir, mode=0775)
        file = open(full_path, mode=mode)
        return file

    def get_size(self):
        """() -> int
        Return the size of the file, measured in bytes, or None if
        the file doesn't exist.
        """
        path = self.get_full_path()
        if not os.path.exists(path):
            return None
        stats = os.stat(path)
        return stats.st_size


class QonFile(StoredFile):
    pass

class QonDir(GenericDB):
    """A simple container of QonFiles and QonDirs"""
    root_class = PersistentList
    
    def __init__(self):
        GenericDB.__init__(self)
        self.filename = None      # same field name as QonFile(StoredFile)
        
    def append(self, val):
        self.root.append(val)
        
    def extend(self, val):
        self.root.extend(val)
        
    def remove(self, val):
        self.root.remove(val)
    
class FileDB(GenericDB):
    
    _initial_quota = 10*1024*1024
    _max_size_of_single_file = 2*1024*1024

    def __init__(self, group, root_dir=None):
        GenericDB.__init__(self)
        self.group = group
        self.quota = self._initial_quota
        self.dirs = QonDir()
        
        if root_dir is None:
            site = os.environ.get('SITE')
            if site:
                config = site_util.get_config()
                root_dir = config.get(site, 'file-store',
                    fallback='/tmp')
            else:
                root_dir = '/tmp'
        self.root_dir = root_dir
        
    def get_file(self, path):
        return self[path]
        
    def _generate_path(self):
        """Generate random path based on current time. Unique only for this
        process.
        """
        global _last_name
        while 1:
            now = str(long(10*time.time()))
            if now != _last_name:
                break
            time.sleep(0.1)
        _last_name = now
        path = '%s/%s/%s/' % (now[-1], now[-3:-1], now)
        return path
        
    def _create_file(self, path, root_dir, source_path):
        # create a new file object
        sf = QonFile(path, self.root_dir, source_path=source_path)
        
        return sf
        
    def new_file(self, source_path=None, dir=None):
        """Create a new file and add to the database.
        Returns a new QonFile object.
        """
        
        # generate a new path
        while 1:
            path = self._generate_path()
            if not self.root.has_key(path):
                break
        
        # create a new file object
        sf = self._create_file(path, self.root_dir, source_path)
        
        # add file to db
        self.add_file(sf, dir)
        return sf
        
    def replace_file(self, path, source_path=None, dir=None):
        """Replace a file already in DB with key 'path' with given source_path."""

        # remove old QonFile from DB
        # must remove first so that _create_file can recreate it with the same path
        self.remove_file(self.get_file(path), unlink=True, dir=dir)
        
        # create new file
        sf = self._create_file(path, self.root_dir, source_path)
        
        # add new QonFile to DB
        self.add_file(sf, dir)
        return sf

    def add_file(self, stored_file, dir=None):
        self[stored_file.path] = stored_file
        if dir is None:
            dir = self.dirs
        dir.append(stored_file)
        self._v_total_size = 0

    def remove_file(self, stored_file, unlink=False, dir=None):
        del self[stored_file.path]
        if dir is None:
            dir = self.dirs
        dir.remove(stored_file)
        if unlink:
            os.unlink(stored_file.get_full_path())
        self._v_total_size = 0
    
    def new_dir(self, parent_dir=None):
        if parent_dir is None:
            parent_dir = self.dirs
        new_dir = QonDir()
        new_dir.filename = 'New Folder'
        parent_dir.append(new_dir)
        return new_dir
        
    def del_dir(self, dir, parent_dir=None):
        # FIXME if dir is non-empty, files are orphaned
        if parent_dir is None:
            parent_dir = self.dirs
        parent_dir.remove(dir)
        
    def list_contents(self, dir=None):
        if dir is None:
            dir = self.dirs
        return dir[:]
    
    def is_empty(self, dir=None):
        if dir is None:
            dir = self.dirs
        return not len(dir)

    def total_size(self):
        """Return total size in bytes of all files in db."""
        if hasattr(self, '_v_total_size') and self._v_total_size:
            return self._v_total_size
            
        size = 0
        for k, sf in self.root.items():
            size += sf.get_size() or 0

        self._v_total_size = size
        return size
        
    def has_room(self, pathname):
        """True if quota will not be exceeded by adding given pathname."""
        stats = os.stat(pathname)
        if stats.st_size + self.total_size() > self.quota:
            return False
        else:
            return True

    def get_maximum_size(self):
        """ returns max size in MB """
        return _max_size_of_single_file / 1024 / 1024

    def exceeds_maximum_size(self, pathname):
        """True if size is too big.  Helps prevent long uploads that hang the server."""
        stats = os.stat(pathname)
        return stat.st_size > _max_size_of_single_file

    def move_files(self, files, destination):
        """Moves files from their current directories and places them in
        the destination folder."""
        if (not files) or (len(files)==0) or (destination is None) or (not isinstance(destination, QonDir)):
            return
        self._orphan_files(self.dirs, files)
        for f in files:
            destination.append(f)

    def _orphan_files(self, dir, files):
        """Removes the files from their parent directories, thereby orphaning them.
        Used by move_files()."""
        entries = dir[:]
        entries.reverse()   # so that the remove() below is safe
        for e in entries:
            if e in files:
                dir.remove(e)
            if isinstance(e, QonDir):
                self._orphan_files(e, files)
            
