#
# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
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

from testtools import TestCase
from tempfile import NamedTemporaryFile

from heat_cfntools.cfntools import cfn_helper


class TestCfnHelper(TestCase):

    def _check_metadata_content(self, content, value):
        with NamedTemporaryFile() as metadata_info:
            metadata_info.write(content)
            metadata_info.flush()
            port = cfn_helper.metadata_server_port(metadata_info.name)
            self.assertEquals(value, port)

    def test_metadata_server_port(self):
        self._check_metadata_content("http://172.20.42.42:8000\n", 8000)

    def test_metadata_server_port_https(self):
        self._check_metadata_content("https://abc.foo.bar:6969\n", 6969)

    def test_metadata_server_port_noport(self):
        self._check_metadata_content("http://172.20.42.42\n", None)

    def test_metadata_server_port_justip(self):
        self._check_metadata_content("172.20.42.42", None)

    def test_metadata_server_port_weird(self):
        self._check_metadata_content("::::", None)
        self._check_metadata_content("beforecolons:aftercolons", None)

    def test_metadata_server_port_emptyfile(self):
        self._check_metadata_content("\n", None)
        self._check_metadata_content("", None)

    def test_metadata_server_nofile(self):
        random_filename = self.getUniqueString()
        self.assertEquals(None,
                          cfn_helper.metadata_server_port(random_filename))

    def test_to_boolean(self):
        self.assertTrue(cfn_helper.to_boolean(True))
        self.assertTrue(cfn_helper.to_boolean('true'))
        self.assertTrue(cfn_helper.to_boolean('yes'))
        self.assertTrue(cfn_helper.to_boolean('1'))
        self.assertTrue(cfn_helper.to_boolean(1))

        self.assertFalse(cfn_helper.to_boolean(False))
        self.assertFalse(cfn_helper.to_boolean('false'))
        self.assertFalse(cfn_helper.to_boolean('no'))
        self.assertFalse(cfn_helper.to_boolean('0'))
        self.assertFalse(cfn_helper.to_boolean(0))
        self.assertFalse(cfn_helper.to_boolean(None))
        self.assertFalse(cfn_helper.to_boolean('fingle'))

    def test_parse_creds_file(self):
        def parse_creds_test(file_contents, creds_match):
            with NamedTemporaryFile(mode='w') as fcreds:
                fcreds.write(file_contents)
                fcreds.flush()
                creds = cfn_helper.parse_creds_file(fcreds.name)
                self.assertDictEqual(creds_match, creds)
        parse_creds_test(
            'AWSAccessKeyId=foo\nAWSSecretKey=bar\n',
            {'AWSAccessKeyId': 'foo', 'AWSSecretKey': 'bar'}
        )
        parse_creds_test(
            'AWSAccessKeyId =foo\nAWSSecretKey= bar\n',
            {'AWSAccessKeyId': 'foo', 'AWSSecretKey': 'bar'}
        )
        parse_creds_test(
            'AWSAccessKeyId    =    foo\nAWSSecretKey    =    bar\n',
            {'AWSAccessKeyId': 'foo', 'AWSSecretKey': 'bar'}
        )
