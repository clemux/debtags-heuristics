import os
import os.path
import re
import rfc822
from debian import debtags, deb822
import logging
import collections
import utils

log = logging.getLogger(__name__)

class DataSource(object):
    def __init__(self, datafile, **kw):
        self.datafile = datafile

    @classmethod
    def create(cls, datadir, **kw):
        if cls.FILENAME:
            datafile = os.path.join(datadir, cls.FILENAME)
            if not os.path.exists(datafile):
                return None
        else:
            datafile = None
        return cls(datafile, **kw)

Pkg = collections.namedtuple("Pkg", ("name", "ver", "src", "sec", "sdesc", "ldesc", "archs",
                                     "predeps", "deps", "recs", "suggs", "enhs", "dist"))

class BinPackages(DataSource):
    """
    Binary package information
    """
    FILENAME = "all-merged"

    def load(self, **kw):
        re_multivalue = re.compile(r'\s*,\s*')

        self.by_name = dict()
        self.by_section = dict()

        log.info("Loading %s...", self.datafile)
        with open(self.datafile, "r") as fd:
            for pkg in deb822.Deb822.iter_paragraphs(fd):
                name = pkg["Package"]
                src = pkg.get("Source", name)
                if not src: src = name

                section = pkg.get("Section", "unknown")
                section = section.split("/")[-1]

                desc = pkg.get("Description", None)
                if desc is None: continue
                sdesc, ldesc = utils.splitdesc(desc)

                def mv(name):
                    "Get list value for multivalue field"
                    return [x for x in re_multivalue.split(pkg.get(name, "")) if x]

                # Cook the source info and make a dict with what we need
                info = Pkg(name, pkg["Version"], src, section, sdesc, ldesc,
                           mv("Architecture"), mv("Pre-Depends"), mv("Depends"),
                           mv("Recommends"), mv("Suggests"), mv("Enhances"), mv("Distribution"))

                # Index it by various attributes
                self.by_name[name] = info
                self.by_section.setdefault(section, []).append(info)

Src = collections.namedtuple("Src", ("name", "ver", "maint", "upls", "bd", "bdi"))

class SrcPackages(DataSource):
    """
    Source package information
    """
    FILENAME = "all-merged-sources"

    def load(self, **kw):
        # Do nothing here: we load on demand
        pass

    def sources(self):
        log.info("Loading %s...", self.datafile)
        re_multivalue = re.compile(r'\s*,\s*')
        with open(self.datafile, "r") as fd:
            for src in deb822.Deb822.iter_paragraphs(fd):
                name = src["Package"]
                mname, memail = rfc822.parseaddr(src.get("Maintainer", ""))

                uploaders = src.get("Uploaders", None)
                if uploaders is not None:
                    uploaders = list(rfc822.AddressList(uploaders))
                else:
                    uploaders = []

                def mv(name):
                    "Get list value for multivalue field"
                    return [x for x in re_multivalue.split(src.get(name, "")) if x]

                yield Src(name, src["Version"], (mname, memail), uploaders,
                          mv("Build-Depends"), mv("Build-Depends-Indep"))


Facet = collections.namedtuple("Facet", ("name", "sdesc", "ldesc"))
Tag = collections.namedtuple("Tag", ("name", "facet", "sdesc", "ldesc"))

class Vocabulary(DataSource):
    """
    Source package information
    """
    FILENAME = "vocabulary"

    def load(self, **kw):
        self.facets = dict()
        self.tags = dict()

        log.info("Loading %s...", self.datafile)
        with open(self.datafile, "r") as fd:
            for voc in deb822.Deb822.iter_paragraphs(fd):
                if "Facet" in voc:
                    name = voc["Facet"]
                    sdesc, ldesc = utils.splitdesc(voc.get("Description", None))
                    self.facets[name] = Facet(name, sdesc, ldesc)
                elif "Tag" in voc:
                    name = voc["Tag"]
                    if name.find("::") == -1:
                        # Skip legacy tags
                        continue
                    facet = self.facets[name.split("::")[0]]
                    sdesc, ldesc = utils.splitdesc(voc.get("Description", None))
                    self.tags[name] = Tag(name, facet, sdesc, ldesc)
                else:
                    log.warning("Found a record in vocabulary that is neither a Facet nor a Tag")

class Popcon(DataSource):
    """
    Popcon votes
    """
    FILENAME = "popcon"

    def load(self, **kw):
        self.votes = dict()

        log.info("Loading %s...", self.datafile)
        with open(self.datafile, "r") as fd:
            for line in fd:
                # Skip comments
                if line[0] == '#': continue
                # Terminate before the totals
                if line[0] == '-': break
                # Split the line
                rank, name, inst, vote, rest = line.split(None, 4)
                # Store the mapping
                self.votes[name] = int(vote)

class StableTags(DataSource):
    """
    Stable tags
    """
    FILENAME = "tags-stable"

    def load(self, **kw):
        self.db = debtags.DB()
        log.info("Loading %s...", self.datafile)
        with open(self.datafile, "r") as fd:
            self.db.read(fd)

class UnstableTags(StableTags):
    """
    Unstable tags
    """
    FILENAME = "tags-unstable"

class Sources(dict):
    """
    All available data sources, by name
    """

    def __init__(self, datadir, **kw):
        """
        Instantiate those sources for which we have data files
        """
        self.sources = []
        for cls in BinPackages, SrcPackages, Vocabulary, Popcon, StableTags, UnstableTags:
            src = cls.create(datadir, **kw)
            if src is not None:
                self[cls.__name__.lower()] = src
                self.sources.append(src)

    def override(self, src, name=None):
        """
        Add a new data source, or override an existing one
        """
        if name is None: name = src.__class__.__name__.lower()
        old = self.get(name, None)
        self[name] = src
        if old is not None:
            self.sources[self.sources.index(old)] = src
        else:
            self.sources.append(src)

    def load(self, **kw):
        """
        Load data sources
        """
        for src in self.sources:
            src.load(**kw)

class Action(object):
    def __init__(self, sources, **kw):
        self.sources = sources
        for k in self.NEED_SOURCES:
            setattr(self, "src_" + k, sources[k])

    @classmethod
    def create(cls, sources, **kw):
        # Validate that we have enough data to run this action
        for s in cls.NEED_SOURCES:
            if s not in sources:
                return None
        return cls(sources, **kw)

