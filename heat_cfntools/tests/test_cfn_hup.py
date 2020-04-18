#
# Copyright 2013 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import tempfile
from unittest import mock

import fixtures
import testtools

from heat_cfntools.cfntools import cfn_helper


class TestCfnHup(testtools.TestCase):

    def setUp(self):
        super(TestCfnHup, self).setUp()
        self.logger = self.useFixture(fixtures.FakeLogger())
        self.stack_name = self.getUniqueString()
        self.resource = self.getUniqueString()
        self.region = self.getUniqueString()
        self.creds = tempfile.NamedTemporaryFile()
        self.metadata = cfn_helper.Metadata(self.stack_name,
                                            self.resource,
                                            credentials_file=self.creds.name,
                                            region=self.region)
        self.init_content = self.getUniqueString()
        self.init_temp = tempfile.NamedTemporaryFile()
        self.service_name = self.getUniqueString()
        self.init_section = {'AWS::CloudFormation::Init': {
            'config': {
                'services': {
                    'sysvinit': {
                        self.service_name: {
                            'enabled': True,
                            'ensureRunning': True,
                        }
                    }
                },
                'files': {
                    self.init_temp.name: {
                        'content': self.init_content
                    }
                }
            }
        }
        }

    def _mock_retrieve_metadata(self, desired_metadata):
        with mock.patch.object(
                cfn_helper.Metadata, 'remote_metadata') as mock_method:
            mock_method.return_value = desired_metadata
            with tempfile.NamedTemporaryFile() as last_md:
                self.metadata.retrieve(last_path=last_md.name)

    def _test_cfn_hup_metadata(self, metadata):

        self._mock_retrieve_metadata(metadata)
        FakeServicesHandler = mock.Mock()
        FakeServicesHandler.monitor_services.return_value = None
        self.useFixture(
            fixtures.MonkeyPatch(
                'heat_cfntools.cfntools.cfn_helper.ServicesHandler',
                FakeServicesHandler))

        section = self.getUniqueString()
        triggers = 'post.add,post.delete,post.update'
        path = 'Resources.%s.Metadata' % self.resource
        runas = 'root'
        action = '/bin/sh -c "true"'
        hook = cfn_helper.Hook(section, triggers, path, runas, action)

        with mock.patch.object(cfn_helper.Hook, 'event') as mock_method:
            mock_method.return_value = None
            self.metadata.cfn_hup([hook])

    def test_cfn_hup_empty_metadata(self):
        self._test_cfn_hup_metadata({})

    def test_cfn_hup_cfn_init_metadata(self):
        self._test_cfn_hup_metadata(self.init_section)
