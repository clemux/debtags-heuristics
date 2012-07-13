import textwrap
import tempfile
import os.path
from cStringIO import StringIO

# From http://code.activestate.com/recipes/363602-lazy-property-evaluation/
class lazy_property(object):
    """
    Lazily evaluated const member
    """
    def __init__(self, calculate_function):
        self._calculate = calculate_function

    def __get__(self, obj, _=None):
        if obj is None:
            return self
        value = self._calculate(obj)
        setattr(obj, self._calculate.func_name, value)
        return value

class atomic_writer(object):
    """
    Atomically write to a file
    """
    def __init__(self, fname, mode=0664, sync=True):
        self.fname = fname
        self.mode = mode
        self.sync = sync
        dirname = os.path.dirname(self.fname)
        self.outfd = tempfile.NamedTemporaryFile(dir=dirname)

    def __enter__(self):
        return self.outfd

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.outfd.flush()
            if self.sync:
                os.fdatasync(self.outfd.fileno())
            os.fchmod(self.outfd.fileno(), self.mode)
            os.rename(self.outfd.name, self.fname)
            self.outfd.delete = False
        self.outfd.close()
        return False

def splitdesc(text):
    if text is None:
        return "", ""
    desc = text.split("\n", 1)
    if len(desc) == 2:
        return desc[0], textwrap.dedent(desc[1])
    else:
        return desc[0], ""

def tags_to_facets(seq):
    """
    Convert a sequence of tags into a sequence of facets.

    Note that no attempt is made to remove duplicates from the facet sequence.
    """
    for t in seq:
        yield t.split("::")[0]

class Sequence(object):
    def __init__(self):
        self.val = 0
    def next(self):
        self.val += 1
        return self.val

class HTMLDescriptionRenderer(object):
    def __init__(self):
        self.output = StringIO()
        self.cur_item = None

    def add_line(self, line):
        if len(line) < 1: return

        if line[0] == ".":
            if len(line) == 1:
                self.add_emptyline()
            else:
                return
        elif line[0].isspace():
            self.add_verbatim(line)
        else:
            self.add_text(line)

    def add_description(self, desc):
        for line in desc.split("\n"):
            self.add_line(line)
        self.done()
        return self.output.getvalue()

    def _open_item(self, name):
        """
        If there is an item which is not @name, close it, then open item @name

        Returns True if the item is just open, False if we continue it
        """
        if self.cur_item != name:
            if self.cur_item is not None:
                print >>self.output, "</%s>" % self.cur_item
            self.cur_item = name
            print >>self.output, "<%s>" % self.cur_item
            return True
        return False

    def _close_item(self):
        if self.cur_item is not None:
            print >>self.output, "</%s>" % self.cur_item
            self.cur_item = None

    def add_emptyline(self):
        # close <p> or <pre>
        self._close_item()

    def add_verbatim(self, line):
        self._open_item("pre")
        print >>self.output, line.encode("utf-8")

    def add_text(self, line):
        if self._open_item("p"):
            self.output.write(line.strip().encode("utf-8"))
        else:
            self.output.write(" %s" % line.strip().encode("utf-8"))

    def done(self):
        self._close_item()

    @classmethod
    def format(cls, desc):
        return cls().add_description(desc)
