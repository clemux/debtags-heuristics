import re

class CheckEngine(object):
    TAGCHECKERS = [None] * 10

    @classmethod
    def register(cls, chk):
        """
        Register a tag checker in the system
        """
        fid = chk.ID
        if fid >= len(cls.TAGCHECKERS):
            # Extend if needed
            cls.TAGCHECKERS.extend([None] * (fid - len(cls.TAGCHECKERS) + 5))
        if cls.TAGCHECKERS[fid] is not None:
            raise KeyError("Tagchecker ID %d already in use for %s" % (fid, cls.TAGCHECKERS[fid].__name__))
        cls.TAGCHECKERS[fid] = chk

    @classmethod
    def by_id(cls, fid):
        """
        Return the tag checker for the given ID
        """
        if fid < len(cls.TAGCHECKERS):
            return cls.TAGCHECKERS[fid]
        return None

    @classmethod
    def list(cls):
        for t in cls.TAGCHECKERS:
            if t is not None:
                yield t

    def __init__(self):
        """
        Initialize the check runner
        """
        self.checks = []

    def refresh(self):
        """
        Load / reload tag checkers at the start of a check run
        """
        # FIXME: call a refresh() method on the checkers instead, so that
        # checkers that need no loaded state can just do nothing, and checkers
        # that load a data file can skip reloading it if it has not changed
        self.checks = []
        for cls in self.TAGCHECKERS:
            if cls is None: continue
            self.checks.append(cls())

    def run(self, tags):
        """
        Run all available checks on the given tagset, generating a sequence of
        (check object, check results) for each check that failed.
        """
        for c in self.checks:
            for res in c.check_tags(tags):
                yield c, res

engine = CheckEngine()

class Tagcheck(object):
    ID = None
    NAME = None  # Check name used to identify this check
    SDESC = None # One line short description
    LDESC = None # Multiline long description
    JS = None
    JS_DATA = None

    @classmethod
    def name(cls):
        res = getattr(cls, "NAME", None)
        if res is None:
            res = cls.__name__
            if res.endswith("Tagcheck"):
                res = res[:-8]
        return res

    @classmethod
    def sdesc(cls):
        return getattr(cls, "SDESC", None)

    @classmethod
    def ldesc(cls):
        return getattr(cls, "LDESC", None)

    @classmethod
    def js_data(cls):
        """
        Return a JavaScript snippet that defines global variables used by this checker
        """
        return cls.JS_DATA

    @classmethod
    def js_check(cls):
        """
        Return a JavaScript snippet that runs this checker
        """
        return cls.JS

class HasRoleTagcheck(Tagcheck):
    ID = 1
    SDESC = "Every package should have a role::* tag"
    JS = """
    if (!tags.hasRE(/^role::/))
        add_check("A <i>role::*</i> tag is still missing.");
    """

    def check_tags(self, tags):
        found = False
        for t in tags:
            if t.startswith("role::"):
                found = True
                break
        if not found:
            yield dict()

    @classmethod
    def format(cls, pkg, data):
        return "A <i>role::*</i> tag is still missing."
CheckEngine.register(HasRoleTagcheck)

class HasUIToolkitTagcheck(Tagcheck):
    ID = 2
    SDESC = "Every package with an X11 or 3D interface should have a uitoolkit::* tag"
    JS = """
    if (tags.hasRE(/^(interface::(3d|x11)|x11::application)$/) && !tags.hasRE(/^uitoolkit::/))
        add_check("An <i>uitoolkit::*</i> tag seems to be missing.");
    """

    def check_tags(self, tags):
        has_iface = None
        for t in tags:
            if t.startswith("uitoolkit::"):
                return
        # There is no uitoolkit:: tag
        for t in ["interface::x11", "interface::3d"]:
            if t in tags:
                has_iface = t
                break
        if has_iface is not None:
            yield dict(found=has_iface)

    @classmethod
    def format(cls, pkg, data):
        return "A <i>uitoolkit::*</i> tag seems to be missing," \
               " since the package has interface %s." % data.get("found", "(undefined)")
CheckEngine.register(HasUIToolkitTagcheck)

class IsReviewedTagcheck(Tagcheck):
    ID = 3
    SDESC = "Package tags should be reviewed by humans"
    JS = """
    if (tags.has("special::not-yet-tagged"))
        add_check("The <i>not-yet-tagged</i> tags are still present.");
    """

    def check_tags(self, tags):
        if "special::not-yet-tagged" in tags:
            yield dict()

    @classmethod
    def format(cls, pkg, data):
        return "The <i>not-yet-tagged</i> tag is still present."
CheckEngine.register(IsReviewedTagcheck)

class HasImplementedInTagcheck(Tagcheck):
    ID = 4
    SDESC = "Every package with a program, devel-lib, plugin, shared-lib, or source role, should have an implemented-in::* tag"
    JS = """
    if (tags.hasRE(/^role::(program|devel-lib|plugin|shared-lib|source)$/) && ! tags.hasRE(/^implemented-in::/))
        add_check("An <i>implemented-in::*</i> tag seems to be missing.");
    """

    re_role = re.compile(r"^role::(program|devel-lib|plugin|shared-lib|source)$")

    def check_tags(self, tags):
        is_sw = None
        for t in tags:
            mo = self.re_role.match(t)
            if mo is not None:
                is_sw = mo.group(1)
            elif t.startswith("implemented-in::"):
                return
        if is_sw is not None:
            yield dict(found=is_sw)

    @classmethod
    def format(cls, pkg, data):
        return "An <i>implemented-in::*</i> tag seems to be missing," \
               " since the package has role %s." % data.get("found", "(undefined)")
CheckEngine.register(HasImplementedInTagcheck)

class HasDevelLangTagcheck(Tagcheck):
    ID = 5
    SDESC = "Every development library should have a devel::lang:* tag"
    JS = """
    if (tags.hasRE(/^(role::devel-lib|devel::library)$/) && ! tags.hasRE(/^devel::lang:/))
        add_check("A <i>devel::lang:*</i> tag seems to be missing.");
    """

    def check_tags(self, tags):
        is_devlib = None
        for t in "role::devel-lib", "devel::library":
            if t in tags:
                is_devlib = t
                break
        if is_devlib is None:
            return

        for t in tags:
            if t.startswith("devel::lang:"):
                return

        yield dict(found=is_devlib)

    @classmethod
    def format(cls, pkg, data):
        return "A <i>devel::lang:*</i> tag seems to be missing," \
               " since the package has tag %s." % data.get("found", "(undefined)")
CheckEngine.register(HasDevelLangTagcheck)

class HasEquivsTagcheck(Tagcheck):
    ID = 6
    SDESC = "role::devel-lib and devel::library should always be together"
    JS = """
    if (tags.has("devel::library") && !tags.has("role::devel-lib"))
    {
        var c = add_check("A <i>role::devel-lib</i> tag seems to be missing.");
        c.add_fix("add role::devel-lib", "+role::devel-lib");
    }
    if (!tags.has("devel::library") && tags.has("role::devel-lib"))
    {
        var c = add_check("A <i>devel::library</i> tag seems to be missing.");
        c.add_fix("add devel::library", "+devel::library");
    }
    """

    def check_tags(self, tags):
        has_role = "role::devel-lib" in tags
        has_devlib = "devel::library" in tags
        if has_role and not has_devlib:
            yield dict(has="role::devel-lib", miss="devel::library")
        elif has_devlib and not has_role:
            yield dict(has="devel::library", miss="role::devel-lib")

    @classmethod
    def format(cls, pkg, data):
        return "A <i>%s</i> tag seems to be missing," \
               " since the package has tag %s." % (
                   data.get("miss", "(undefined)"),
                   data.get("has", "(undefined)"))
CheckEngine.register(HasEquivsTagcheck)

class HasGameTagcheck(Tagcheck):
    ID = 7
    SDESC = "Every package with use::gameplaying should have a game::* tags"
    JS = """
    if (tags.has("use::gameplaying") && !tags.hasRE(/^game::/))
        add_check("A <i>game::*</i> tag seems to be missing.");
    """

    def check_tags(self, tags):
        if "use::gameplaying" not in tags:
            return
        for t in tags:
            if t.startswith("game::"):
                return
        yield dict()

    @classmethod
    def format(cls, pkg, data):
        return "A <i>game::*</i> tag seems to be missing," \
               " since the package has tag use::gameplaying."
CheckEngine.register(HasGameTagcheck)

class DebugSymbolsTagcheck(Tagcheck):
    ID = 9
    SDESC = "Debugging symbols should not have other tags except role::debug-symbols or role::dummy"
    JS = """
    if (tags.has("role::debug-symbols") &&
        !( (tags.size() == 1) || (tags.size() == 2 && tags.has("role::dummy")) ))
    {
        var c = add_check("Packages with debugging symbols should have no tags except <i>role::debug-symbols</i>");
        (function() {
            var to_remove = [];
            tags.each(function(t) {
                if (t != "role::debug-symbols" && t != "role::dummy")
                    to_remove.push(t);
            });
            if (to_remove.length > 0)
            {
                to_remove.sort();
                var patch = [];
                for (var i in to_remove) { patch.push("-" + to_remove[i]); }
                c.add_fix("Remove tags " + to_remove.join(", "), patch.join(", "));
            }
        })()
    }
    """

    def check_tags(self, tags):
        trigger = False
        if "role::debug-symbols" not in tags:
            return
        for t in tags:
            if t not in ("role::debug-symbols", "role::dummy"):
                trigger = True
                break
        if trigger:
            yield dict()

    @classmethod
    def format(cls, pkg, data):
        return "Packages with debugging symbols should have no tags except" \
               " <i>role::debug-symbols</i>"
CheckEngine.register(DebugSymbolsTagcheck)

class ShlibsTagcheck(Tagcheck):
    ID = 10
    SDESC = "Shared libraries should not normally have other tags except implemented-in"
    JS = """
    if (tags.has("role::shared-lib"))
    {
        var extras = [];
        tags.each(function(t) {
            if (t == "role::shared-lib") return;
            if (t == "role::dummy") return;
            if (t.substr(0, 16) == "implemented-in::") return;
            if (t == "x11::library") return;
            extras.push(t)
        });
        if (extras.length > 0)
        {
            var c = add_hint("Shared libraries should not normally have other tags except <i>implemented-in::*</i>");
            extras.sort();
            var patch = [];
            for (var i in extras) { patch.push("-" + extras[i]); }
            c.add_fix("Remove tags " + extras.join(", "), patch.join(", "));
        }
    }
    """

    def check_tags(self, tags):
        trigger = False
        if "role::shared-lib" not in tags:
            return
        extras = []
        for t in tags:
            if t in ("role::shared-lib", "role::dummy", "x11::library"): continue
            if t.startswith("implemented-in::"): continue
            extras.append(t)
        if extras:
            yield dict(t=extras)

    @classmethod
    def format(cls, pkg, data):
        return "Shared libraries should have no tags except" \
                " <i>implemented-in::*</i>"
CheckEngine.register(ShlibsTagcheck)
