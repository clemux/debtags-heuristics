# apriori - wrapper for launching Christian Borgelt's apriori implementation on
#           Debtags data
#
# Copyright (C) 2007--2011  Enrico Zini <enrico@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

# Christian Borgelt's apriori implementation can be found at
# http://borgelt.net/apriori.html

import sys
import os
import os.path
import re
from debian import debtags
from subprocess import Popen, PIPE
import collections

AprioriResult = collections.namedtuple("AprioriResult", ("src", "tgt", "sus", "conf"))

class Apriori(object):
    def __init__(self, quiet=False, **kw):
        """
        Initialize with default parameters

        If reverse is True, the default options will select the rules for
        negative associations (the least confidence, the least likely that the
        association happens)
        """
        self.conf_apriori = "./apriori"
        # Whether apriori's stderr should be redirected to /dev/null
        self.conf_apriori_quiet = quiet
        # Minimum cardinality a tag should have to be fed to apriori
        self.conf_card_threshold = 30
        self.pick_defaults(**kw)

    def pick_defaults(self, reverse=False):
        if not reverse:
            # Default apriori options
            # -s: Minimum support an itemset should have to be considered
            #     If positive, it is a percentage (0.0% ... 100.0%)
            #     If negative, it is an absolute number
            # -c: Minimum confidence for a rule (percentage)
            # -n: Maximum rule size (counting antecedents and consquent together)
            self.conf_apriori_options = ('-s-30', "-c90", "-n3")
            # Function used to filter output rules (by default, accept them all)
            self.conf_filter = lambda r:True
        else:
            # For reverse, use extended rule selection to only pick up
            # 'interesting' negative rules
            self.conf_apriori_options = ('-s-20', "-c0", "-n3", '-en', '-d0.7')
            # And keep only those results with very low confidence (i.e.: 'this
            # almost never happens')
            self.conf_filter = lambda r:r.conf < 1.0

    def run_apriori(self, db):
        """
        Run apriori with the given tag collection, generating AprioriResult
        tuples
        """

        # Compute a blacklist with the tags with insufficient cardinality
        if self.conf_card_threshold:
            whitelist = set(t for t, pkgs in db.iter_tags_packages() if len(pkgs) >= self.conf_card_threshold)
        else:
            whitelist = None

        # Run the algorithm
        cmdline = (self.conf_apriori, "-tr") + self.conf_apriori_options + ("-", "-")
        if self.conf_apriori_quiet:
            with open("/dev/null", "w") as nullfd:
                apriori = Popen(cmdline, stdin=PIPE, stdout=PIPE, stderr=nullfd.fileno())
        else:
            apriori = Popen(cmdline, stdin=PIPE, stdout=PIPE)

        # Feed it the input data
        for pkg, tags in db.iter_packages_tags():
            if whitelist is not None:
                tags = tags & whitelist
            if tags:
                print >>apriori.stdin, " ".join(tags)
        apriori.stdin.close()

        # Read results
        for x in self._parse_apriori_output(apriori.stdout):
            yield x

        # Wait for the program to finish
        status = apriori.wait()
        #  0: success
        # 15: E_NOITEMS
        if status not in [0, 15]:
            raise RuntimeError("%s exited with status %d" % (self.conf_apriori, status))

    def _parse_apriori_output(self, fd):
        """
        Parse the apriori output generating the broken down values
        """
        re_line = re.compile(r"^(\S+)\s+<-\s+(.+?)\s+\(([0-9.]+), ([0-9.]+)\)\s*$")
        for line in fd:
            m = re_line.match(line)
            if not m: continue
            tgt, src, sus, conf = m.groups()
            rule = AprioriResult(frozenset(src.split(' ')), tgt, float(sus), float(conf))
            if self.conf_filter(rule):
                yield rule

    @classmethod
    def read_debtags_db(cls, fname):
        """
        Read a debtags database, filtering out tags that we usually do not want
        in the computation
        """
        db = debtags.DB()
        tag_filter = re.compile(r"^(?:special::.+|.+:special:.+|.+:TODO|.+:todo)$")
        with open(fname, "r") as fd:
            db.read(fd, lambda x: not tag_filter.match(x))
        return db


