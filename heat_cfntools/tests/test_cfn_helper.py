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

import boto.cloudformation as cfn
import json
import mox
import subprocess
import tempfile
import testtools
import testtools.matchers as ttm

from heat_cfntools.cfntools import cfn_helper


class FakePOpen():
    def __init__(self, stdout='', stderr='', returncode=0):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def communicate(self):
        return (self.stdout, self.stderr)

    def wait(self):
        pass


class MockPopenTestCase(testtools.TestCase):

    def mock_cmd_run(self, command, cwd=None, env=None):
        return subprocess.Popen(
            command, cwd=cwd, env=env, stderr=-1, stdout=-1)

    def setUp(self):
        super(MockPopenTestCase, self).setUp()
        self.m = mox.Mox()
        self.m.StubOutWithMock(subprocess, 'Popen')
        self.addCleanup(self.m.UnsetStubs)


class TestCommandRunner(MockPopenTestCase):

    def test_command_runner(self):
        self.mock_cmd_run(['su', 'root', '-c', '/bin/command1']).AndReturn(
            FakePOpen('All good'))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/command2']).AndReturn(
            FakePOpen('Doing something', 'error', -1))
        self.m.ReplayAll()
        cmd2 = cfn_helper.CommandRunner('/bin/command2')
        cmd1 = cfn_helper.CommandRunner('/bin/command1', cmd2)
        cmd1.run('root')
        self.assertEqual(
            'CommandRunner:\n\tcommand: /bin/command1\n\tstdout: All good',
            str(cmd1))
        self.assertEqual(
            'CommandRunner:\n\tcommand: /bin/command2\n\tstatus: -1\n'
            '\tstdout: Doing something\n\tstderr: error',
            str(cmd2))
        self.m.VerifyAll()


class TestCfnHelper(testtools.TestCase):

    def _check_metadata_content(self, content, value):
        with tempfile.NamedTemporaryFile() as metadata_info:
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
            with tempfile.NamedTemporaryFile(mode='w') as fcreds:
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


class TestMetadataRetrieve(testtools.TestCase):

    def test_metadata_retrieve_files(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)

        with tempfile.NamedTemporaryFile() as last_file:
            pass

        with tempfile.NamedTemporaryFile(mode='w+') as default_file:
            default_file.write(md_str)
            default_file.flush()
            self.assertThat(default_file.name, ttm.FileContains(md_str))

            md.retrieve(
                default_path=default_file.name,
                last_path=last_file.name)

            self.assertThat(last_file.name, ttm.FileContains(md_str))
            self.assertDictEqual(md_data, md._metadata)

        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(
            default_path=default_file.name,
            last_path=last_file.name)
        self.assertDictEqual(md_data, md._metadata)

    def test_metadata_retrieve_none(self):

        md = cfn_helper.Metadata('teststack', None)
        with tempfile.NamedTemporaryFile() as last_file:
            pass
        with tempfile.NamedTemporaryFile() as default_file:
            pass

        md.retrieve(
            default_path=default_file.name,
            last_path=last_file.name)
        self.assertIsNone(md._metadata)

    def test_metadata_retrieve_passed(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(meta_str=md_str)
        self.assertDictEqual(md_data, md._metadata)

        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(meta_str=md_data)
        self.assertDictEqual(md_data, md._metadata)
        self.assertEqual(md_str, str(md))

    def test_is_valid_metadata(self):
        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(meta_str=md_data)

        self.assertDictEqual(md_data, md._metadata)
        self.assertTrue(md._is_valid_metadata())
        self.assertDictEqual(
            md_data['AWS::CloudFormation::Init'], md._metadata)

    def test_remote_metadata(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}

        m = mox.Mox()
        m.StubOutWithMock(
            cfn.CloudFormationConnection, 'describe_stack_resource')

        cfn.CloudFormationConnection.describe_stack_resource(
            'teststack', None).MultipleTimes().AndReturn({
                'DescribeStackResourceResponse': {
                    'DescribeStackResourceResult': {
                        'StackResourceDetail': {'Metadata': md_data}}}})

        m.ReplayAll()
        try:
            md = cfn_helper.Metadata(
                'teststack',
                None,
                access_key='foo',
                secret_key='bar')
            md.retrieve()
            self.assertDictEqual(md_data, md._metadata)

            with tempfile.NamedTemporaryFile(mode='w') as fcreds:
                fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n')
                fcreds.flush()
                md = cfn_helper.Metadata(
                    'teststack', None, credentials_file=fcreds.name)
                md.retrieve()
            self.assertDictEqual(md_data, md._metadata)

            m.VerifyAll()
        finally:
            m.UnsetStubs()

    def test_cfn_init(self):

        with tempfile.NamedTemporaryFile(mode='w+') as foo_file:
            md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
                foo_file.name: {"content": "bar"}}}}}

            md = cfn_helper.Metadata('teststack', None)
            md.retrieve(meta_str=md_data)
            md.cfn_init()
            self.assertThat(foo_file.name, ttm.FileContains('bar'))
