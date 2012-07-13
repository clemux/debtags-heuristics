import re
import os.path
import datasources
import patches
import cPickle as pickle

# Set this to a pathname to point to the pickled apriori rule cache
APRIORI_CACHE = None

class RuleSections(datasources.Action):
    NEED_SOURCES = ("binpackages",)

    def make_patch(self):
        for p in self.src_binpackages.by_section.get("libdevel", ()):
            yield p.name, frozenset(("role::devel-lib", "devel::library")), frozenset()

        re_dbg = re.compile("-dbg$")
        for p in self.src_binpackages.by_section.get("debug", ()):
            if re_dbg.match(p.name):
                yield p.name, frozenset(("role::debug-symbols",)), frozenset()

        re_shlib = re.compile("^lib.+[0-9]$")
        for p in self.src_binpackages.by_section.get("libs", ()):
            if re_shlib.match(p.name):
                yield p.name, frozenset(("role::shared-lib",)), frozenset()


class RuleUIToolkit(datasources.Action):
    NEED_SOURCES = ("binpackages",)

    def make_patch(self):
        re_maps = (
            (re.compile("^libgtk"), "uitoolkit::gtk"),
            (re.compile("^libqt[34]"), "uitoolkit::qt"),
            (re.compile("^libsdl[0-9]"), "uitoolkit::sdl"),
            (re.compile("^lesstif[12]"), "uitoolkit::motif"),
            (re.compile("^libncurses"), "uitoolkit::ncurses"),
            (re.compile("^libwxgtk"), "uitoolkit::wxwidgets"),
        )

        for name, pkg in self.src_binpackages.by_name.iteritems():
            # Skip libraries
            if pkg.sec.startswith("lib"): continue

            added = set()
            for dep in pkg.predeps, pkg.deps:
                for deppkg in dep:
                    for regexp, newtag in re_maps:
                        if regexp.match(deppkg):
                            added.add(newtag)
                            break
            if added:
                yield name, added, frozenset()

class RuleKernel(datasources.Action):
    NEED_SOURCES = ("binpackages",)

    def make_patch(self):
        rules = (
            ("devel", (
                ("linux-headers-", ("admin::kernel", "devel::lang:c", "devel::library", "implemented-in::c", "role::devel-lib")),
                ("linux-kbuild-", ("admin::kernel", "implemented-in::c", "implemented-in::perl", "implemented-in::shell")), # role::???
                ("linux-source-", ("admin::kernel", "implemented-in::c", "role::source")),
                ("linux-support-", ("admin::kernel", "devel::lang:c", "devel::library", "implemented-in::c", "role::devel-lib")),
                ("linux-tree-", ("admin::kernel", "role::dummy", "special::meta")),
            )),
            ("doc", (
                ("linux-doc-", ("admin::kernel", "made-of::html", "role::documentation")),
                ("linux-manual-", ("admin::kernel", "made-of::man", "role::documentation")),
            )),
            ("admin", (
                ("linux-image-", ("admin::kernel", "implemented-in::c")), # +role::???
                ("linux-patch-", ("admin::kernel", "role::source")),
            )),
        )

        for section, section_rules in rules:
            for p in self.src_binpackages.by_section.get(section, ()):
                name = p.name
                added = set()
                for prefix, tags in section_rules:
                    if name.startswith(prefix):
                        added.update(tags)
                        break
                if added:
                    yield name, added, frozenset()

class RuleNames(datasources.Action):
    NEED_SOURCES = ("binpackages",)

    def make_patch(self):
        re_maps = (
            (re.compile("^libmono[0-9-].+-cil$"), ("devel::library", "role::devel-lib", "devel::ecma-cli")),
        )
        for name, pkg in self.src_binpackages.by_name.iteritems():
            added = set()
            for regexp, tags in re_maps:
                if regexp.match(name):
                    added.update(tags)
                    break
            if added:
                yield name, added, frozenset()

class RulePerl(datasources.Action):
    NEED_SOURCES = ("binpackages",)

    def make_patch(self):
        re_perllib = re.compile("^lib.+-perl$")

        for p in self.src_binpackages.by_section.get("perl", ()):
            if not re_perllib.match(p.name): continue
            added = set(("devel::lang:perl", "devel::library"))
            if "all" in p.archs:
                added.add("implemented-in::perl")
            else:
                added.add("implemented-in::c")
            yield p.name, added, frozenset()

class RuleApriori(datasources.Action):
    NEED_SOURCES = ("stabletags",)

    def make_patch(self):
        rules = None

        # Load rules database
        if APRIORI_CACHE is None: return
        if os.path.exists(APRIORI_CACHE):
            with open(APRIORI_CACHE) as fd:
                rules = pickle.load(fd)
        if rules is None: return

        # We cannot evaluate facet rules, because they give facet suggestions,
        # not actual tags to add
        rules = rules["t"]

        # Evaluate tag rules
        db = self.src_stabletags.db
        for pkg, tags in db.iter_packages_tags():
            added = set()
            for r in rules:
                if r.src.issubset(tags) and r.tgt not in tags:
                    added.add(r.tgt)
            if added:
                yield pkg, added, frozenset()

class RuleNewVersions(datasources.Action):
    # FIXME: unstabletags is NOT what we expect: it's a possibly obsolete leftover file
    NEED_SOURCES = ("binpackages", "unstabletags")

    def make_patch(self):
        stem_regexps = (
            # Shared libraries
            re.compile(r"^lib(.+?)[0-9.]+$"),
            # Kernel modules
            re.compile(r"^(.+)-modules-[0-9.-]+"),
        )

        # Return the stemmed version of the package name, or None if the
        # package name is not one we handle
        def stem(name):
            for r in stem_regexps:
                mo = r.match(name)
                if mo: return mo.group(1)
            return None

        # Group package names by their stemmed version
        by_stem = dict()
        for name in self.src_binpackages.by_name.iterkeys():
            stemmed = stem(name)
            if stemmed is not None:
                by_stem.setdefault(stemmed, []).append(name)

        # Get the unstable tag database
        db = self.src_unstabletags.db

        # Go through every group with more than 1 member, merging all the tags
        for group in by_stem.itervalues():
            if len(group) < 2: continue

            # Compute the merged tag set
            merged_tags = set()
            merged_tags.update(*(db.tags_of_package(x) for x in group))

            # Remove special::* tags
            specials = frozenset(x for x in merged_tags if x.startswith("special::"))
            merged_tags -= specials

            # In case there were only special tags, we have nothing to do
            if not merged_tags: continue

            # Add tags from the merged tag set to all packages in the group with
            # not-yet-tagged tags
            for pkg in group:
                tags = db.tags_of_package(pkg)

                # Only add tags to not-yet-tagged packages. This prevents
                # generating a patch that, for example, merges the tags of an
                # obsolete library with the new one.
                #
                # This kind of filtering should happen later anyway, but it
                # makes sense to also do it now in case autodebtag patches are
                # used for all packages as tips.
                if 'special::not-yet-tagged' not in tags: continue

                # Add the tags
                added = merged_tags - tags
                if added:
                    yield pkg, added, frozenset()


class Autodebtag(object):
    def __init__(self, sources):
        self.sources = sources
        self.rules = list()

        self.create_rule(RuleSections)
        self.create_rule(RuleUIToolkit)
        self.create_rule(RuleKernel)
        self.create_rule(RuleNames)
        self.create_rule(RulePerl)
        self.create_rule(RuleApriori)
        self.create_rule(RuleNewVersions)

    def create_rule(self, cls):
        rule = cls.create(self.sources)
        if rule is not None:
            self.rules.append(rule)

    def make_patches(self, pkg_whitelist):
        patchset = patches.PatchSet()
        for r in self.rules:
            for pkg, added, removed in r.make_patch():
                if pkg not in pkg_whitelist:
                    continue
                if added or removed:
                    patchset.add(pkg, added, removed)
        return patchset 
