import sys
import os
from distutils import log
from distutils.errors import DistutilsOptionError

from setuptools import Command
from pkg_resources import working_set, parse_version

from pkglib.cmdline import run
from pkglib.setuptools import dependency
from pkglib import pypi
from pkglib import manage

from base import CommandMixin

# These are never updated.
UPDATE_BLACKLIST = [
    'Python',
    'distribute',
    'virtualenv',
    'setuptools',
    'pip',
]


class update(Command, CommandMixin):
    """ Update package and dependencies to latest versions """
    description = "Update package and dependencies to latest versions."
    command_consumes_arguments = True

    user_options = [
        ('dev', None, 'Will install dev packages if they are available. ' \
                      'Set implicitly if this is run as `python setup.py update`.'),
        ('third-party', 't', 'Include third-party packages'),
        ('source', 's', 'Update only source checkouts'),
        ('eggs', 'e', 'Update only eggs'),
        ('everything', 'E', 'Update all currently installed packages unless they are pinned.'),
        ('no-cleanup', None, 'Skip cleanup of site-packages'),
        ("index-url=", "i", "base URL of Python Package Index"),
    ]
    boolean_options = [
        'dev',
        'everything',
        'third_party',
        'source',
        'eggs',
        'no-cleanup',
    ]

    exclusions = []

    def initialize_options(self):
        self.args = []
        self.dev = False
        self.everything = False
        self.third_party = False
        self.both = True
        self.source = False
        self.eggs = False
        self.ascii = False
        self.exclusions = UPDATE_BLACKLIST[:]
        self.no_cleanup = False
        self.index_url = False

    def finalize_options(self):
        if self.eggs or self.source:
            self.both = False
        if self.both:
            self.eggs = True
            self.source = True

        self.pypi_client = pypi.PyPi(self.get_finalized_command('upload').repository)

    def run(self):
        if self.distribution.get_name() == 'UNKNOWN' and not self.args:
            raise DistutilsOptionError('Please specify some packages to update.')

        if self.distribution.get_name() != 'UNKNOWN':
            log.info("Setting dev mode as this has been run from a setup.py file")
            self.dev = True

        # These are all the packages that could possibly be updated
        all_packages = dependency.all_packages(exclusions=self.exclusions,
                                               include_third_party=self.third_party,
                                               )
        full_name_list = [i.project_name for i in working_set]

        log.debug("All: %r" % all_packages.keys())

        # These are the root packages to update. If none were passed in, use
        # this command's distribution.
        roots = []
        if self.args:
            for i in self.args:
                if not i in full_name_list:
                    raise DistutilsOptionError("Unknown package: %s" % i)
                if not i in all_packages:
                    raise DistutilsOptionError("Unable to update package %s, it is pinned (See list above)." % i)
            roots = self.args

        if not roots:
            roots = [self.distribution.get_name()]

        source_targets, egg_targets = dependency.get_targets(roots, all_packages, everything=self.everything,
                                                             immediate_deps=True, follow_all=True,
                                                             include_eggs=self.eggs, include_source=self.source)
        # Filter egg targets for upgrading
        egg_targets = self.filter_upgrades(egg_targets)

        # Update as required.
        if source_targets:
            self.banner("Source targets")
            log.info('\n'.join(source_targets))
        if egg_targets:
            self.banner("Egg targets")
            log.info('\n'.join(egg_targets))

        if not egg_targets and not source_targets:
            log.info("No targets to update")

        # Check for open files
        self.check_open_files(egg_targets)

        # Important Run-Time Order!
        # 1) update source checkouts and re-create the egg_info dir. This
        #    is very important so the requires.txt is up-to-date
        [self.update_source(all_packages[i]) for i in source_targets]

        # 2) Pull in the latest versions of any non-pinned eggs
        # TODO: During this run, the 'pinned packages' list may actually change.
        #       This is the case when you're updating a prod graph to a dev graph.
        #       It would be nice to figure out these changes before printing the list
        #       of pinned packages earlier, otherwise you have to run the command
        #       twice to get the correct behavior.

        # Make sure egg targets get done in the right order:
        self.update_egg_packages(egg_targets)

        # 3) Re-setup.py develop all the source checkouts.
        [self.develop_source(all_packages[i]) for i in source_targets]

        if not self.no_cleanup:
            self.run_cleanup_in_subprocess()

    def check_open_files(self, egg_targets):
        """ Check for open files in the egg targets """
        dists = [i for i in working_set if i.project_name in egg_targets]

        def is_open(f):
            for egg_dir in [i.location for i in dists]:
                if f[1].startswith(egg_dir):
                    return True
            return False

        open_files = [i for i in self.get_open_files() if is_open(i)]
        if open_files:
            err = ["Can't update whilst the following files and directories remain open:"]
            for pid, fname in open_files:
                err.append("%s %s" % ("(pid %0.10s)" % pid, fname))
            raise DistutilsOptionError('\n'.join(err))

    def filter_upgrades(self, egg_targets):
        """ Exclude packages where the latest version on pypi is lower than
            the currently installed version.
        """
        def is_upgrade(package):
            if package not in working_set.by_key:
                return True
            current_version = working_set.by_key[package].version

            # TODO: get revision numbers from server so we can skip the auto-upgrade
            #       of dev versions even if they haven't changed.
            if manage.is_dev_version(current_version):
                return True
            last_version = self.pypi_client.get_last_version(package, self.dev)
            # Pypi does not return any versions for this package.
            if not last_version:
                return False
            return parse_version(current_version) < parse_version(last_version)

        return [et for et in egg_targets if is_upgrade(et)]

    def update_egg_packages(self, egg_targets):
        """
        Updates egg packages
        """
        # This is a lazy import to support bootstrapping pkglib
        from pkglib.setuptools.buildout import install

        self.banner("Updating egg packages: %s" % ' '.join(egg_targets))
        if self.dev:
            self.execute(install, [self.get_easy_install_cmd(index_url=self.index_url),
                                    egg_targets,
                                    False, # add_to_global,
                                    False, # prefer_final,
                                    True], # force_upgrade
                        "Updating %s (will use dev packages)" % ' '.join(egg_targets),
                        not self.verbose)
        else:
            self.execute(install, [self.get_easy_install_cmd(index_url=self.index_url),
                                    egg_targets,
                                    False, # add_to_global,
                                    True, # prefer_final,
                                    True], # force_upgrade
                        "Updating %s (will use released packages)" % ' '.join(egg_targets),
                        not self.verbose)

    def update_source(self, pkg):
        """
        Updates a single source checkout and run ``egg_info`` to update the
        requirements file.
        """
        self.banner("Updating source checkout: %s" % pkg.project_name)
        self.execute(run, (['svn', 'up', pkg.location], None, not self.verbose),
            msg="Updating source checkout at %s" % pkg.location)
        cmd = [sys.executable, os.path.join(pkg.location, 'setup.py'), 'egg_info']
        if self.index_url:
            cmd.extend(['-i', self.index_url])
        self.execute(run, (cmd, None, not self.verbose),
            msg="Running setup.py egg_info for %s" % pkg.project_name)

    def develop_source(self, pkg):
        """
        Runs ``setup.py develop`` for a single source checkout
        """
        self.banner("Setting up source package: %s" % pkg.project_name)
        cmd = [sys.executable, os.path.join(pkg.location, 'setup.py'), 'develop']
        if self.dev:
            if self.index_url:
                cmd.extend(['-i', self.index_url])
            self.execute(run, (cmd, None, not self.verbose),
                msg="Running setup.py develop for %s" % pkg.project_name)
        else:
            cmd.append('--prefer-final')
            if self.index_url:
                cmd.extend(['-i', self.index_url])
            self.execute(run, (cmd, None, not self.verbose),
                msg="Running setup.py develop for %s (final versions only)" % pkg.project_name)
