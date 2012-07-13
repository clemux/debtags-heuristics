import utils
import itertools
import re

class Patch(object):
    """
    A patch to the tagset of a package
    """
    def __init__(self, text=None, blacklist_tags=[]):
        self.added = set()
        self.removed = set()
        if text is not None:
            self.parse(text, blacklist_tags=blacklist_tags)

    def empty(self):
        """
        Return True if this patch does not contain any changes
        """
        return not (self.added or self.removed)

    def parse(self, text, blacklist_tags=[]):
        for t in text.split(", "):
            tag = t[1:]
            if tag in blacklist_tags: continue
            if tag is None: continue
            if t[0] == '+':
                self.added.add(tag)
            elif t[0] == '-':
                self.removed.add(tag)

    def apply(self, pkg, tagdb):
        """
        Apply the patch to the given package and debtags.DB
        """
        ts = tagdb.db.setdefault(pkg, set())
        ts -= self.removed
        ts |= self.added
        for t in self.removed:
            tagdb.rdb.setdefault(t, set()).discard(pkg)
        for t in self.added:
            tagdb.rdb.setdefault(t, set()).add(pkg)

    def write(self, fd):
        bits = ['-' + t for t in sorted(self.removed)]
        bits += ['+' + t for t in sorted(self.added)]
        fd.write(", ".join(bits))

    def __str__(self):
        return ", ".join(itertools.chain(
            ('+' + t for t in sorted(self.added)),
            ('-' + t for t in sorted(self.removed))))

    def add(self, added=frozenset(), removed=frozenset()):
        """
        Merge changes into this patch
        """
        self.added |= added
        self.removed -= added
        self.removed |= removed
        self.added -= removed

    def simplified(self, tags, tag_whitelist=None):
        """
        Return a new patch with only those changes that actually apply to the
        given tag set.

        It can return the same patch of all changes apply, or it can return
        None if no changes apply.
        """
        new_add = self.added - tags
        new_del = self.removed.intersection(tags)
        if tag_whitelist:
            new_add &= tag_whitelist
            new_del &= tag_whitelist
        if not new_add and not new_del:
            return None
        if new_add == self.added and new_del == self.removed:
            return self
        res = Patch()
        res.added = new_add
        res.removed = new_del
        return res

    def diff(self, patch):
        """
        Return a patch that can be applied after this one so that the effect is
        as if the given patch had been applied
        """
        res = Patch()
        res.added = self.removed - patch.removed
        res.added |= patch.added - self.added
        res.removed = self.added - patch.added
        res.removed |= patch.removed - self.removed
        return res


class PatchSet(dict):
    """
    pkg->patch mapping containing a set of patches
    """
    def __init__(self, fname=None, fd=None, blacklist_tags=[]):
        if fname is not None:
            self.read(fname, blacklist_tags=blacklist_tags)
        elif fd is not None:
            self.read_fd(fd, blacklist_tags=blacklist_tags)

    def empty(self):
        """
        Return True if this patchset does not contain any changes
        """
        for p in self.itervalues():
            if not p.empty():
                return False
        return True

    def read(self, fname, blacklist_tags=[]):
        with open(fname) as fd:
            self.read_fd(fd, blacklist_tags=blacklist_tags)

    def read_fd(self, fd, blacklist_tags=[]):
        for line in fd:
            line = line.strip()
            if not line: continue
            try:
                pkg, tags = line.split(": ", 1)
            except ValueError:
                # Gracefully ignore package names with empty patches
                if re.match(r"^[^: ,]+:?$", line):
                    continue
                raise ValueError("Cannot parse line '%s'" % line)
            if pkg in self:
                self[pkg].parse(tags, blacklist_tags=blacklist_tags)
            else:
                patch = Patch(tags, blacklist_tags=blacklist_tags)
                if not patch.empty():
                    self[pkg] = patch

    def write_fd(self, fd):
        for pkg, patch in self.iteritems():
            fd.write(pkg)
            fd.write(": ")
            patch.write(fd)
            fd.write("\n")

    def write_atomically(self, fname):
        with utils.atomic_writer(fname) as fd:
            self.write_fd(fd)

    def apply_to(self, tagdb):
        """
        Apply patchset to a debtags.DB
        """
        for pkg, patch in self.iteritems():
            patch.apply(pkg, tagdb)

    def add(self, pkg, added=frozenset(), removed=frozenset()):
        """
        Add a patch to this patchset
        """
        if pkg in self:
            self[pkg].add(added, removed)
        else:
            patch = Patch()
            patch.added = added
            patch.removed = removed
            if not patch.empty():
                self[pkg] = patch

    def add_patchset(self, patchset):
        """
        Merge a patchset on top of this one
        """
        for pkg, patch in patchset.iteritems():
            self.add(pkg, patch.added, patch.removed)

    def simplified(self, tagdb, tag_whitelist=None):
        """
        Return a new patchset with only those changes that actually apply to
        the given tag database.

        It can return the same patchset of all changes apply, or it can return
        None if no changes apply.
        """
        res = PatchSet()
        for pkg, patch in self.iteritems():
            # Skip packages that do not exist anymore
            if not tagdb.has_package(pkg):
                continue
            tags = tagdb.tags_of_package(pkg)
            new_patch = patch.simplified(tags, tag_whitelist)
            if new_patch is not None:
                res[pkg] = new_patch
        return res

    def diff(self, patchset):
        """
        Return the patchset that can be applied after this one so that the
        effect is as if the given patchset had been applied
        """
        res = PatchSet()

        for pkg, patch in self.iteritems():
            opatch = patchset.get(pkg, None)
            if opatch is None:
                # Add the reverse of this patch
                res.add(pkg, patch.removed, patch.added)
            else:
                diff = patch.diff(opatch)
                res.add(pkg, diff.added, diff.removed)

        for pkg, patch in patchset.iteritems():
            if pkg not in self:
                res.add(pkg, patch.added, patch.removed)

        return res

    @property
    def summary_packages(self):
        """
        Return a sorted list of package names affected by this patch
        """
        res = self.keys()
        res.sort()
        return res

    @property
    def summary_tags(self):
        """
        Return a sorted list of tag names affected by this patch
        """
        tags = set()
        for p in self.itervalues():
            tags |= p.added
            tags |= p.removed
        return sorted(tags)

    @property
    def sorted_for_presentation(self):
        res = []
        for pkg, patch in sorted(self.iteritems()):
            res.append((pkg, sorted(patch.added), sorted(patch.removed)))
        return res

    def affects(self, pkgs):
        for p in pkgs:
            if p in self:
                return True
        return False

    def __str__(self):
        return "\n".join((k + ": " + str(v)) for k, v in self.iteritems())

    def __repr__(self):
        return "\n".join((k + ": " + str(v)) for k, v in self.iteritems())
