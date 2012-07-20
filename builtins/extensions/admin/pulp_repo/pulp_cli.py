# -*- coding: utf-8 -*-
#
# Copyright © 2012 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

from pulp.client.extensions.extensions import PulpCliSection, PulpCliCommand, PulpCliOption, PulpCliFlag, UnknownArgsParser
from pulp.bindings.exceptions import NotFoundException
from pulp.client.extensions.search import SearchCommand
from pulp.server.db.model.criteria import Criteria

# -- framework hook -----------------------------------------------------------

def initialize(context):
    context.cli.add_section(RepoSection(context))

# -- sections -----------------------------------------------------------------

class RepoSection(PulpCliSection):

    def __init__(self, context):
        """
        @param context:
        @type  context: pulp.client.extensions.core.ClientContext
        """
        PulpCliSection.__init__(self, 'repo', 'repository lifecycle (create, delete, configure, etc.) commands')

        self.context = context
        self.prompt = context.prompt # for easier access

        # Common Options
        id_option = PulpCliOption('--id', 'uniquely identifies the repository; only alphanumeric, -, and _ allowed', required=True)
        name_option = PulpCliOption('--display-name', '(optional) user-readable display name for the repository', required=False)
        description_option = PulpCliOption('--description', '(optional) user-readable description for the repository', required=False)

        # Create Command
        create_command = PulpCliCommand('create', 'creates a new repository', self.create)
        create_command.add_option(id_option)
        create_command.add_option(name_option)
        create_command.add_option(description_option)
        self.add_command(create_command)

        # Update Command
        update_command = PulpCliCommand('update', 'changes metadata on an existing repository', self.update)
        update_command.add_option(id_option)
        update_command.add_option(name_option)
        update_command.add_option(description_option)
        self.add_command(update_command)

        # Delete Command
        delete_command = PulpCliCommand('delete', 'deletes a repository', self.delete)
        delete_command.add_option(PulpCliOption('--id', 'identifies the repository to be deleted', required=True))
        self.add_command(delete_command)

        # List Command
        list_command = PulpCliCommand('list', 'lists repositories on the Pulp server', self.list)
        list_command.add_option(PulpCliFlag('--summary', 'if specified, only a minimal amount of repository information is displayed'))
        list_command.add_option(PulpCliOption('--fields', 'comma-separated list of repository fields; if specified, only the given fields will displayed', required=False))
        list_command.add_option(PulpCliFlag('--importers', 'if specified, importer configuration is displayed'))
        list_command.add_option(PulpCliFlag('--distributors', 'if specified, the list of distributors and their configuration is displayed'))
        self.add_command(list_command)

        # Search Command
        self.add_command(SearchCommand(self.search))

        # List Units Command
        units_command = PulpCliCommand('units', 'lists content units in the repository', self.units)
        units_command.add_option(id_option)
        self.add_command(units_command)

        # Subsections
        self.add_subsection(ImporterSection(context))
        self.add_subsection(SyncSection(context))
        self.add_subsection(RepoGroupSection(context))

    def create(self, **kwargs):

        # Collect input
        id = kwargs['id']
        name = id
        if 'display-name' in kwargs:
            name = kwargs['display-name']
        description = kwargs['description']
        notes = None # TODO: add support later

        # Call the server
        self.context.server.repo.create(id, name, description, notes)
        self.prompt.render_success_message('Repository [%s] successfully created' % id)

    def update(self, **kwargs):

        # Assemble the delta for all options that were passed in
        delta = dict([(k, v) for k, v in kwargs.items() if v is not None])
        delta.pop('id') # not needed in the delta

        try:
            self.context.server.repo.update(kwargs['id'], {'delta' : delta})
            self.prompt.render_success_message('Repository [%s] successfully updated' % kwargs['id'])
        except NotFoundException:
            self.prompt.write('Repository [%s] does not exist on the server' % kwargs['id'], tag='not-found')

    def delete(self, **kwargs):
        id = kwargs['id']

        try:
            self.context.server.repo.delete(id)
            self.prompt.render_success_message('Repository [%s] successfully deleted' % id)
        except NotFoundException:
            self.prompt.write('Repository [%s] does not exist on the server' % id, tag='not-found')

    def list(self, **kwargs):
        """
        :param summary: If True, equivalent to setting fields='id,display-name'.
                        If False, no effect.
        :type  summary: bool

        :param fields:  comma-separated field names as a string, specifying
                        which fields will be returned. This is a required
                        parameter unless you pass summary=True.
        :type fields:   str

        :param importers:   If any value that evaluates to True, include the
                            repo's importers in the output.

        :param distributors:    If any value that evaluates to True, include
                                the repo's distributors in the output.
        """

        # This needs to be revisited. For the sake of time, the repo list in
        # rpm_repo will be hacked up for yum repositories specifically. Later
        # we can revisit this output for the generic case.
        # jdob, March 12, 2012

        self.prompt.render_title('Repositories')

        # Default flags to render_document_list
        filters = None
        order = ['id', 'display_name', 'description', 'content_unit_count']

        if kwargs['summary'] is True:
            filters = ['id', 'display-name']
            order = filters
        elif kwargs['fields'] is not None:
            filters = kwargs['fields'].split(',')
            if 'id' not in filters:
                filters.append('id')
            order = ['id']

        query_params = {}

        for param in ('importers', 'distributors'):
            if kwargs.get(param):
                query_params[param] = True
                filters.append(param)

        repo_list = self.context.server.repo.repositories(query_params).response_body

        for repo in repo_list:
            self.prompt.render_document(repo, filters=filters, order=order)

    def search(self, **kwargs):
        criteria = Criteria.from_client_input(kwargs)
        repo_list = self.context.server.repo_search.search(criteria)
        for repo in repo_list:
            self.prompt.render_document(repo)

    def units(self, **kwargs):
        repo_id = kwargs['id']
        self.prompt.render_title('Units in Repository [%s]' % repo_id)

        query = {}
        units = self.context.server.repo_unit_search.search(repo_id, query)

        def header_func(i):
            return '-----------'
        filters = ['unit_type_id', 'unit_id', 'owner_type', 'owner_id', 'created', 'updated', 'repo_id', 'metadata']
        order = filters
        self.prompt.render_document_list(units.response_body, header_func=header_func, filters=filters, order=order)

class ImporterSection(PulpCliSection):

    def __init__(self, context):
        PulpCliSection.__init__(self, 'importer', 'manage importers for existing repositories')
        self.context = context
        self.prompt = context.prompt

        # Add Importer Command
        required_options = [
            ('--id', 'identifies the repository'),
            ('--type_id', 'identifies the type of importer being added'),
        ]
        add_parser = UnknownArgsParser(self.prompt, 'repo add', required_options)
        self.add_command(PulpCliCommand('add', 'adds an importer to a repository', self.add_importer, parser=add_parser))

    def add_importer(self, **kwargs):
        repo_id = kwargs.pop('id')
        importer_type_id = kwargs.pop('type_id')

        # Everything left in kwargs is considered part of the importer config
        self.context.server.repo_importer.create(repo_id, importer_type_id, kwargs)
        self.prompt.render_success_message('Successfully added importer of type [%s] to repository [%s]' % (importer_type_id, repo_id))

class SyncSection(PulpCliSection):

    def __init__(self, context):
        PulpCliSection.__init__(self, 'sync', 'run, schedule, or view the status of sync operations')
        self.context = context
        self.prompt = context.prompt

        # Run an Immediate Sync
        run_command = PulpCliCommand('run', 'triggers an immediate sync of a specific repository', self.run)
        run_command.add_option(PulpCliOption('--id', 'identifies the repository to sync', required=True))
        self.add_command(run_command)

        # TODO: Add sync schedule and status commands

    def run(self, **kwargs):

        repo_id = kwargs['id']
        self.prompt.render_paragraph('Synchronizing repository [%s]' % repo_id)

        spinner = self.prompt.create_threaded_spinner()
        spinner.start()
        try:
            # TODO: Replace with unknown arg parsing and allow for sync override config
            self.context.server.repo_actions.sync(repo_id, None)
        finally:
            spinner.stop()

        self.prompt.render_success_message('Repository sync completed for repository [%s]' % repo_id)


class RepoGroupSection(PulpCliSection):
    def __init__(self, context):
        PulpCliSection.__init__(self, 'group', 'repository group commands')

        self.context = context
        self.prompt = context.prompt # for easier access

        # Common Options
        id_option = PulpCliOption('--id', 'uniquely identifies the repo group; only alphanumeric, -, and _ allowed', required=True)
        name_option = PulpCliOption('--display-name', 'user-readable display name for the repo group', required=False)
        description_option = PulpCliOption('--description', 'user-readable description for the repo group', required=False)

        # Create Command
        create_command = PulpCliCommand('create', 'creates a new repository group', self.create)
        create_command.add_option(id_option)
        create_command.add_option(name_option)
        create_command.add_option(description_option)
        self.add_command(create_command)

        # Update Command
        update_command = PulpCliCommand('update', 'changes metadata on an existing repo group', self.update)
        update_command.add_option(id_option)
        update_command.add_option(name_option)
        update_command.add_option(description_option)
        d =  'adds/updates/deletes notes to programmatically identify the repo group; '
        d += 'key-value pairs must be separated by an equal sign (e.g. key=value); multiple notes can '
        d += 'be changed by specifying this option multiple times; notes are deleted by '
        d += 'specifying "" as the value'
        update_command.add_option(PulpCliOption('--note', d, required=False, allow_multiple=True))
        self.add_command(update_command)

        # Delete Command
        delete_command = PulpCliCommand('delete', 'deletes a repository group', self.delete)
        delete_command.add_option(PulpCliOption('--id', 'identifies the repository group to be deleted', required=True))
        self.add_command(delete_command)

        # List Command
        list_command = PulpCliCommand('list', 'lists summary of repo groups registered to the Pulp server', self.list)
        list_command.add_option(PulpCliFlag('--details', 'if specified, all the repo group information is displayed'))
        list_command.add_option(PulpCliOption('--fields', 'comma-separated list of repo group fields; if specified, only the given fields will displayed', required=False))
        self.add_command(list_command)

        # Search Command
        self.add_command(SearchCommand(self.search))

    def create(self, **kwargs):
        # Collect input
        id = kwargs['id']
        name = id
        if 'display-name' in kwargs:
            name = kwargs['display-name']
        description = kwargs['description']
        notes = None # TODO: add support later

        # Call the server
        self.context.server.repo_group.create(id, name, description, notes)
        self.prompt.render_success_message('Repository Group [%s] successfully created' % id)

    def update(self, **kwargs):
        # Assemble the delta for all options that were passed in
        delta = dict([(k, v) for k, v in kwargs.items() if v is not None])
        delta.pop('id') # not needed in the delta

        try:
            self.context.server.repo_group.update(kwargs['id'], delta)
            self.prompt.render_success_message('Repo group [%s] successfully updated' % kwargs['id'])
        except NotFoundException:
            self.prompt.write('Repo group [%s] does not exist on the server' % kwargs['id'], tag='not-found')

    def delete(self, **kwargs):
        id = kwargs['id']

        try:
            self.context.server.repo_group.delete(id)
            self.prompt.render_success_message('Repository group [%s] successfully deleted' % id)
        except NotFoundException:
            self.prompt.write('Repository group [%s] does not exist on the server' % id, tag='not-found')

    def list(self, **kwargs):
        self.prompt.render_title('Repository Groups')

        repo_group_list = self.context.server.repo_group.repo_groups().response_body

        # Default flags to render_document_list
        filters = ['id', 'display_name', 'description', 'repo_ids', 'notes']
        order = filters

        if kwargs['fields'] is not None:
            filters = kwargs['fields'].split(',')
            if 'id' not in filters:
                filters.append('id')
            order = ['id']

        # Manually loop over the repositories so we can interject the plugins
        # manually based on the CLI flags.
        for repo_group in repo_group_list:
            self.prompt.render_document(repo_group, filters=filters, order=order)

    def search(self, **kwargs):
        criteria = Criteria.from_client_input(kwargs)
        repo_group_list = self.context.server.repo_group_search.search(criteria)
        for consumer in repo_group_list:
            self.prompt.render_document(consumer)
