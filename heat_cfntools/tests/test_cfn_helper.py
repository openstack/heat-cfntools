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
import fixtures
import json
from mox3 import mox
import os
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

    def mock_unorder_cmd_run(self, command, cwd=None, env=None):
        return subprocess.Popen(
            command, cwd=cwd, env=env, stderr=-1, stdout=-1).InAnyOrder()

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


class TestPackages(MockPopenTestCase):

    def test_yum_install(self):
        install_list = []
        for pack in ('httpd', 'wordpress', 'mysql-server'):
            self.mock_unorder_cmd_run(
                ['su', 'root', '-c', 'rpm -q %s' % pack]) \
                .AndReturn(FakePOpen(returncode=1))
            self.mock_unorder_cmd_run(
                ['su', 'root', '-c',
                 'yum -y --showduplicates list available %s' % pack]) \
                .AndReturn(FakePOpen(returncode=0))
            install_list.append(pack)

        # This mock call corresponding to 'su root -c yum -y install .*'
        # But there is no way to ignore the order of the parameters, so only
        # check the return value.
        self.mock_cmd_run(mox.IgnoreArg()).AndReturn(FakePOpen(
            returncode=0))

        self.m.ReplayAll()
        packages = {
            "yum": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        cfn_helper.PackagesHandler(packages).apply_packages()
        self.m.VerifyAll()

    def test_zypper_install(self):
        install_list = []
        for pack in ('httpd', 'wordpress', 'mysql-server'):
            self.mock_unorder_cmd_run(
                ['su', 'root', '-c', 'rpm -q %s' % pack]) \
                .AndReturn(FakePOpen(returncode=1))
            self.mock_unorder_cmd_run(
                ['su', 'root', '-c',
                 'zypper -n --no-refresh search %s' % pack]) \
                .AndReturn(FakePOpen(returncode=0))
            install_list.append(pack)

        # This mock call corresponding to 'su root -c zypper -n install .*'
        # But there is no way to ignore the order of the parameters, so only
        # check the return value.
        self.mock_cmd_run(mox.IgnoreArg()).AndReturn(FakePOpen(
            returncode=0))

        self.m.ReplayAll()
        packages = {
            "zypper": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        cfn_helper.PackagesHandler(packages).apply_packages()
        self.m.VerifyAll()

    def test_apt_install(self):
        # This mock call corresponding to
        # 'DEBIAN_FRONTEND=noninteractive su root -c apt-get -y install .*'
        # But there is no way to ignore the order of the parameters, so only
        # check the return value.
        self.mock_cmd_run(mox.IgnoreArg()).AndReturn(FakePOpen(
            returncode=0))
        self.m.ReplayAll()

        packages = {
            "apt": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        cfn_helper.PackagesHandler(packages).apply_packages()
        self.m.VerifyAll()


class TestServicesHandler(MockPopenTestCase):

    def test_services_handler_systemd(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(True)
        # apply_services
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl enable httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl enable mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start mysqld.service']
        ).AndReturn(FakePOpen())

        # monitor_services not running
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())

        # monitor_services running
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen())

        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "systemd": {
                "mysqld": {"enabled": "true", "ensureRunning": "true"},
                "httpd": {"enabled": "true", "ensureRunning": "true"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()
        # services not running
        sh.monitor_services()

        # services running
        sh.monitor_services()

        self.m.VerifyAll()

    def test_services_handler_systemd_disabled(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(True)
        # apply_services
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl disable httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl stop httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl disable mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_unorder_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl stop mysqld.service']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "systemd": {
                "mysqld": {"enabled": "false", "ensureRunning": "false"},
                "httpd": {"enabled": "false", "ensureRunning": "false"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()

        self.m.VerifyAll()

    def test_services_handler_sysv_service_chkconfig(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(False)
        os.path.exists('/sbin/service').MultipleTimes().AndReturn(True)
        os.path.exists('/sbin/chkconfig').MultipleTimes().AndReturn(True)
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/chkconfig httpd on']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd start']
        ).AndReturn(FakePOpen())

        # monitor_services not running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd start']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())

        # monitor_services running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "httpd": {"enabled": "true", "ensureRunning": "true"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()
        # services not running
        sh.monitor_services()

        # services running
        sh.monitor_services()

        self.m.VerifyAll()

    def test_services_handler_sysv_disabled_service_chkconfig(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(False)
        os.path.exists('/sbin/service').MultipleTimes().AndReturn(True)
        os.path.exists('/sbin/chkconfig').MultipleTimes().AndReturn(True)
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/chkconfig httpd off']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd stop']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "httpd": {"enabled": "false", "ensureRunning": "false"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()

        self.m.VerifyAll()

    def test_services_handler_sysv_systemctl(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(True)
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl enable httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start httpd.service']
        ).AndReturn(FakePOpen())

        # monitor_services not running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())

        # monitor_services running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "httpd": {"enabled": "true", "ensureRunning": "true"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()
        # services not running
        sh.monitor_services()

        # services running
        sh.monitor_services()

        self.m.VerifyAll()

    def test_services_handler_sysv_disabled_systemctl(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(True)
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl disable httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl stop httpd.service']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "httpd": {"enabled": "false", "ensureRunning": "false"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()

        self.m.VerifyAll()

    def test_services_handler_sysv_service_updaterc(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(False)
        os.path.exists('/sbin/service').MultipleTimes().AndReturn(False)
        os.path.exists('/sbin/chkconfig').MultipleTimes().AndReturn(False)
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/update-rc.d httpd enable']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/service httpd status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/service httpd start']
        ).AndReturn(FakePOpen())

        # monitor_services not running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/service httpd status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/service httpd start']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())

        # monitor_services running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/service httpd status']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "httpd": {"enabled": "true", "ensureRunning": "true"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()
        # services not running
        sh.monitor_services()

        # services running
        sh.monitor_services()

        self.m.VerifyAll()

    def test_services_handler_sysv_disabled_service_updaterc(self):
        self.m.StubOutWithMock(os.path, 'exists')
        os.path.exists('/bin/systemctl').MultipleTimes().AndReturn(False)
        os.path.exists('/sbin/service').MultipleTimes().AndReturn(False)
        os.path.exists('/sbin/chkconfig').MultipleTimes().AndReturn(False)
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/update-rc.d httpd disable']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/service httpd status']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/usr/sbin/service httpd stop']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "httpd": {"enabled": "false", "ensureRunning": "false"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()

        self.m.VerifyAll()


class TestHupConfig(MockPopenTestCase):

    def test_load_main_section(self):
        fcreds = tempfile.NamedTemporaryFile()
        fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n')
        fcreds.flush()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write('''[main]
stack=teststack
credential-file=%s''' % fcreds.name)
        main_conf.flush()
        mainconfig = cfn_helper.HupConfig([open(main_conf.name)])
        self.assertEqual(
            '{stack: teststack, credential_file: %s, '
            'region: nova, interval:10}' % fcreds.name,
            str(mainconfig))
        main_conf.close()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write('''[main]
stack=teststack
region=region1
credential-file=%s-invalid
interval=120''' % fcreds.name)
        main_conf.flush()
        e = self.assertRaises(Exception, cfn_helper.HupConfig,
                              [open(main_conf.name)])
        self.assertIn('invalid credentials file', str(e))
        fcreds.close()

    def test_hup_config(self):
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/cfn-http-restarted']).AndReturn(
                FakePOpen('All good'))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/hook1']).AndReturn(
            FakePOpen('All good'))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/hook2']).AndReturn(
            FakePOpen('All good'))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/hook3']).AndReturn(
            FakePOpen('All good'))
        self.m.ReplayAll()

        hooks_conf = tempfile.NamedTemporaryFile()

        def write_hook_conf(f, name, triggers, path, action):
            f.write(
                '[%s]\ntriggers=%s\npath=%s\naction=%s\nrunas=root\n\n' % (
                    name, triggers, path, action))

        write_hook_conf(
            hooks_conf,
            'hook2',
            'service2.restarted',
            'Resources.resource2.Metadata',
            '/bin/hook2')
        write_hook_conf(
            hooks_conf,
            'hook1',
            'service1.restarted',
            'Resources.resource1.Metadata',
            '/bin/hook1')
        write_hook_conf(
            hooks_conf,
            'hook3',
            'service3.restarted',
            'Resources.resource3.Metadata',
            '/bin/hook3')
        write_hook_conf(
            hooks_conf,
            'cfn-http-restarted',
            'service.restarted',
            'Resources.resource.Metadata',
            '/bin/cfn-http-restarted')
        hooks_conf.flush()

        fcreds = tempfile.NamedTemporaryFile()
        fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n')
        fcreds.flush()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write('''[main]
stack=teststack
credential-file=%s
region=region1
interval=120''' % fcreds.name)
        main_conf.flush()

        mainconfig = cfn_helper.HupConfig([
            open(main_conf.name),
            open(hooks_conf.name)])
        unique_resources = mainconfig.unique_resources_get()
        self.assertThat([
            'resource',
            'resource1',
            'resource2',
            'resource3',
        ], ttm.Equals(sorted(unique_resources)))

        hooks = sorted(mainconfig.hooks,
                       key=lambda hook: hook.resource_name_get())
        self.assertEqual(len(hooks), 4)
        self.assertEqual(
            '{cfn-http-restarted, service.restarted,'
            ' Resources.resource.Metadata, root, /bin/cfn-http-restarted}',
            str(hooks[0]))
        self.assertEqual(
            '{hook1, service1.restarted, Resources.resource1.Metadata,'
            ' root, /bin/hook1}', str(hooks[1]))
        self.assertEqual(
            '{hook2, service2.restarted, Resources.resource2.Metadata,'
            ' root, /bin/hook2}', str(hooks[2]))
        self.assertEqual(
            '{hook3, service3.restarted, Resources.resource3.Metadata,'
            ' root, /bin/hook3}', str(hooks[3]))

        for hook in hooks:
            hook.event(hook.triggers, None, hook.resource_name_get())

        hooks_conf.close()
        fcreds.close()
        main_conf.close()
        self.m.VerifyAll()


class TestCfnHelper(testtools.TestCase):

    def _check_metadata_content(self, content, value):
        with tempfile.NamedTemporaryFile() as metadata_info:
            metadata_info.write(content)
            metadata_info.flush()
            port = cfn_helper.metadata_server_port(metadata_info.name)
            self.assertEqual(value, port)

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
        self.assertEqual(None,
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
                self.assertThat(creds_match, ttm.Equals(creds))
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

    def setUp(self):
        super(TestMetadataRetrieve, self).setUp()
        self.tdir = self.useFixture(fixtures.TempDir())
        self.last_file = os.path.join(self.tdir.path, 'last_metadata')

    def test_metadata_retrieve_files(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)

        with tempfile.NamedTemporaryFile(mode='w+') as default_file:
            default_file.write(md_str)
            default_file.flush()
            self.assertThat(default_file.name, ttm.FileContains(md_str))

            self.assertTrue(
                md.retrieve(default_path=default_file.name,
                            last_path=self.last_file))

            self.assertThat(self.last_file, ttm.FileContains(md_str))
            self.assertThat(md_data, ttm.Equals(md._metadata))

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(md.retrieve(default_path=default_file.name,
                                    last_path=self.last_file))
        self.assertThat(md_data, ttm.Equals(md._metadata))

    def test_metadata_retrieve_none(self):

        md = cfn_helper.Metadata('teststack', None)
        default_file = os.path.join(self.tdir.path, 'default_file')

        self.assertFalse(md.retrieve(default_path=default_file,
                                     last_path=self.last_file))
        self.assertIsNone(md._metadata)

        displayed = self.useFixture(fixtures.StringStream('stdout'))
        fake_stdout = displayed.stream
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', fake_stdout))
        md.display()
        fake_stdout.flush()
        self.assertEqual(displayed.getDetails()['stdout'].as_text(), "")

    def test_metadata_retrieve_passed(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(md.retrieve(meta_str=md_data,
                                    last_path=self.last_file))
        self.assertThat(md_data, ttm.Equals(md._metadata))
        self.assertEqual(md_str, str(md))

        displayed = self.useFixture(fixtures.StringStream('stdout'))
        fake_stdout = displayed.stream
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', fake_stdout))
        md.display()
        fake_stdout.flush()
        self.assertEqual(displayed.getDetails()['stdout'].as_text(),
                         "{\"AWS::CloudFormation::Init\": {\"config\": {"
                         "\"files\": {\"/tmp/foo\": {\"content\": \"bar\"}"
                         "}}}}\n")

    def test_metadata_retrieve_by_key_passed(self):

        md_data = {"foo": {"bar": {"fred.1": "abcd"}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(md.retrieve(meta_str=md_data,
                                    last_path=self.last_file))
        self.assertThat(md_data, ttm.Equals(md._metadata))
        self.assertEqual(md_str, str(md))

        displayed = self.useFixture(fixtures.StringStream('stdout'))
        fake_stdout = displayed.stream
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', fake_stdout))
        md.display("foo")
        fake_stdout.flush()
        self.assertEqual(displayed.getDetails()['stdout'].as_text(),
                         "{\"bar\": {\"fred.1\": \"abcd\"}}\n")

    def test_metadata_retrieve_by_nested_key_passed(self):

        md_data = {"foo": {"bar": {"fred.1": "abcd"}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(md.retrieve(meta_str=md_data,
                                    last_path=self.last_file))
        self.assertThat(md_data, ttm.Equals(md._metadata))
        self.assertEqual(md_str, str(md))

        displayed = self.useFixture(fixtures.StringStream('stdout'))
        fake_stdout = displayed.stream
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', fake_stdout))
        md.display("foo.bar.'fred.1'")
        fake_stdout.flush()
        self.assertEqual(displayed.getDetails()['stdout'].as_text(),
                         '"abcd"\n')

    def test_metadata_retrieve_key_none(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(md.retrieve(meta_str=md_data,
                                    last_path=self.last_file))
        self.assertThat(md_data, ttm.Equals(md._metadata))
        self.assertEqual(md_str, str(md))

        displayed = self.useFixture(fixtures.StringStream('stdout'))
        fake_stdout = displayed.stream
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', fake_stdout))
        md.display("no_key")
        fake_stdout.flush()
        self.assertEqual(displayed.getDetails()['stdout'].as_text(), "")

    def test_metadata_retrieve_by_nested_key_none(self):

        md_data = {"foo": {"bar": {"fred.1": "abcd"}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(md.retrieve(meta_str=md_data,
                                    last_path=self.last_file))
        self.assertThat(md_data, ttm.Equals(md._metadata))
        self.assertEqual(md_str, str(md))

        displayed = self.useFixture(fixtures.StringStream('stdout'))
        fake_stdout = displayed.stream
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', fake_stdout))
        md.display("foo.fred")
        fake_stdout.flush()
        self.assertEqual(displayed.getDetails()['stdout'].as_text(), "")

    def test_metadata_retrieve_by_nested_key_none_with_matching_string(self):

        md_data = {"foo": "bar"}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(md.retrieve(meta_str=md_data,
                                    last_path=self.last_file))
        self.assertThat(md_data, ttm.Equals(md._metadata))
        self.assertEqual(md_str, str(md))

        displayed = self.useFixture(fixtures.StringStream('stdout'))
        fake_stdout = displayed.stream
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', fake_stdout))
        md.display("foo.bar")
        fake_stdout.flush()
        self.assertEqual(displayed.getDetails()['stdout'].as_text(), "")

    def test_metadata_creates_cache(self):
        temp_home = tempfile.mkdtemp()

        def cleanup_temp_home(thome):
            os.unlink(os.path.join(thome, 'cache', 'last_metadata'))
            os.rmdir(os.path.join(thome, 'cache'))
            os.rmdir(os.path.join(thome))

        self.addCleanup(cleanup_temp_home, temp_home)

        last_path = os.path.join(temp_home, 'cache', 'last_metadata')
        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)
        md = cfn_helper.Metadata('teststack', None)

        self.assertFalse(os.path.exists(last_path),
                         "last_metadata file already exists")
        self.assertTrue(md.retrieve(meta_str=md_str, last_path=last_path))
        self.assertTrue(os.path.exists(last_path),
                        "last_metadata file should exist")
        # Ensure created dirs and file have right perms
        self.assertTrue(os.stat(last_path).st_mode & 0o600 == 0o600)
        self.assertTrue(
            os.stat(os.path.dirname(last_path)).st_mode & 0o700 == 0o700)

    def test_is_valid_metadata(self):
        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(
            md.retrieve(meta_str=md_data, last_path=self.last_file))

        self.assertThat(md_data, ttm.Equals(md._metadata))
        self.assertTrue(md._is_valid_metadata())
        self.assertThat(
            md_data['AWS::CloudFormation::Init'], ttm.Equals(md._metadata))

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
            self.assertTrue(md.retrieve(last_path=self.last_file))
            self.assertThat(md_data, ttm.Equals(md._metadata))

            with tempfile.NamedTemporaryFile(mode='w') as fcreds:
                fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n')
                fcreds.flush()
                md = cfn_helper.Metadata(
                    'teststack', None, credentials_file=fcreds.name)
                self.assertTrue(md.retrieve(last_path=self.last_file))
            self.assertThat(md_data, ttm.Equals(md._metadata))

            m.VerifyAll()
        finally:
            m.UnsetStubs()

    def test_nova_meta_with_cache(self):
        meta_in = {"uuid": "f9431d18-d971-434d-9044-5b38f5b4646f",
                   "availability_zone": "nova",
                   "hostname": "as-wikidatabase-4ykioj3lgi57.novalocal",
                   "launch_index": 0,
                   "meta": {},
                   "public_keys": {"heat_key": "ssh-rsa etc...\n"},
                   "name": "as-WikiDatabase-4ykioj3lgi57"}
        md_str = json.dumps(meta_in)

        md = cfn_helper.Metadata('teststack', None)
        with tempfile.NamedTemporaryFile(mode='w+') as default_file:
            default_file.write(md_str)
            default_file.flush()
            self.assertThat(default_file.name, ttm.FileContains(md_str))
            meta_out = md.get_nova_meta(cache_path=default_file.name)

            self.assertEqual(meta_in, meta_out)

    def test_nova_meta_curl(self):
        url = 'http://169.254.169.254/openstack/2012-08-10/meta_data.json'
        temp_home = tempfile.mkdtemp()
        cache_path = os.path.join(temp_home, 'meta_data.json')

        def cleanup_temp_home(thome):
            os.unlink(cache_path)
            os.rmdir(thome)

        self.m = mox.Mox()
        self.addCleanup(self.m.UnsetStubs)
        self.addCleanup(cleanup_temp_home, temp_home)

        meta_in = {"uuid": "f9431d18-d971-434d-9044-5b38f5b4646f",
                   "availability_zone": "nova",
                   "hostname": "as-wikidatabase-4ykioj3lgi57.novalocal",
                   "launch_index": 0,
                   "meta": {"freddy": "is hungry"},
                   "public_keys": {"heat_key": "ssh-rsa etc...\n"},
                   "name": "as-WikiDatabase-4ykioj3lgi57"}
        md_str = json.dumps(meta_in)

        def write_cache_file(*params, **kwargs):
            with open(cache_path, 'w+') as cache_file:
                cache_file.write(md_str)
                cache_file.flush()
                self.assertThat(cache_file.name, ttm.FileContains(md_str))

        self.m.StubOutWithMock(subprocess, 'Popen')
        subprocess.Popen(['su', 'root', '-c',
                          'curl -o %s %s' % (cache_path, url)],
                         cwd=None, env=None, stderr=-1, stdout=-1)\
                  .WithSideEffects(write_cache_file)\
                  .AndReturn(FakePOpen('Downloaded', '', 0))

        self.m.ReplayAll()

        md = cfn_helper.Metadata('teststack', None)
        meta_out = md.get_nova_meta(cache_path=cache_path)
        self.assertEqual(meta_in, meta_out)
        self.m.VerifyAll()

    def test_nova_meta_curl_corrupt(self):
        url = 'http://169.254.169.254/openstack/2012-08-10/meta_data.json'
        temp_home = tempfile.mkdtemp()
        cache_path = os.path.join(temp_home, 'meta_data.json')

        def cleanup_temp_home(thome):
            os.unlink(cache_path)
            os.rmdir(thome)

        self.m = mox.Mox()
        self.addCleanup(self.m.UnsetStubs)
        self.addCleanup(cleanup_temp_home, temp_home)

        md_str = "this { is not really json"

        def write_cache_file(*params, **kwargs):
            with open(cache_path, 'w+') as cache_file:
                cache_file.write(md_str)
                cache_file.flush()
                self.assertThat(cache_file.name, ttm.FileContains(md_str))

        self.m.StubOutWithMock(subprocess, 'Popen')
        subprocess.Popen(['su', 'root', '-c',
                          'curl -o %s %s' % (cache_path, url)],
                         cwd=None, env=None, stderr=-1, stdout=-1)\
                  .WithSideEffects(write_cache_file)\
                  .AndReturn(FakePOpen('Downloaded', '', 0))

        self.m.ReplayAll()

        md = cfn_helper.Metadata('teststack', None)
        meta_out = md.get_nova_meta(cache_path=cache_path)
        self.assertEqual(None, meta_out)
        self.m.VerifyAll()

    def test_nova_meta_curl_failed(self):
        url = 'http://169.254.169.254/openstack/2012-08-10/meta_data.json'
        temp_home = tempfile.mkdtemp()
        cache_path = os.path.join(temp_home, 'meta_data.json')

        def cleanup_temp_home(thome):
            os.rmdir(thome)

        self.m = mox.Mox()
        self.addCleanup(self.m.UnsetStubs)
        self.addCleanup(cleanup_temp_home, temp_home)

        self.m.StubOutWithMock(subprocess, 'Popen')
        subprocess.Popen(['su', 'root', '-c',
                          'curl -o %s %s' % (cache_path, url)],
                         cwd=None, env=None, stderr=-1, stdout=-1)\
                  .AndReturn(FakePOpen('Failed', '', 1))

        self.m.ReplayAll()

        md = cfn_helper.Metadata('teststack', None)
        meta_out = md.get_nova_meta(cache_path=cache_path)
        self.assertEqual(None, meta_out)
        self.m.VerifyAll()

    def test_get_tags(self):
        self.m = mox.Mox()
        self.addCleanup(self.m.UnsetStubs)

        fake_tags = {'foo': 'fee',
                     'apple': 'red'}
        md_data = {"uuid": "f9431d18-d971-434d-9044-5b38f5b4646f",
                   "availability_zone": "nova",
                   "hostname": "as-wikidatabase-4ykioj3lgi57.novalocal",
                   "launch_index": 0,
                   "meta": fake_tags,
                   "public_keys": {"heat_key": "ssh-rsa etc...\n"},
                   "name": "as-WikiDatabase-4ykioj3lgi57"}
        tags_expect = fake_tags
        tags_expect['InstanceId'] = md_data['uuid']

        md = cfn_helper.Metadata('teststack', None)

        self.m.StubOutWithMock(md, 'get_nova_meta')
        md.get_nova_meta().AndReturn(md_data)
        self.m.ReplayAll()

        tags = md.get_tags()
        self.assertEqual(tags_expect, tags)
        self.m.VerifyAll()

    def test_get_instance_id(self):
        self.m = mox.Mox()
        self.addCleanup(self.m.UnsetStubs)

        uuid = "f9431d18-d971-434d-9044-5b38f5b4646f"
        md_data = {"uuid": uuid,
                   "availability_zone": "nova",
                   "hostname": "as-wikidatabase-4ykioj3lgi57.novalocal",
                   "launch_index": 0,
                   "public_keys": {"heat_key": "ssh-rsa etc...\n"},
                   "name": "as-WikiDatabase-4ykioj3lgi57"}

        md = cfn_helper.Metadata('teststack', None)

        self.m.StubOutWithMock(md, 'get_nova_meta')
        md.get_nova_meta().AndReturn(md_data)
        self.m.ReplayAll()

        self.assertEqual(md.get_instance_id(), uuid)
        self.m.VerifyAll()


class TestCfnInit(MockPopenTestCase):

    def setUp(self):
        super(TestCfnInit, self).setUp()
        self.tdir = self.useFixture(fixtures.TempDir())
        self.last_file = os.path.join(self.tdir.path, 'last_metadata')

    def test_cfn_init(self):

        with tempfile.NamedTemporaryFile(mode='w+') as foo_file:
            md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
                foo_file.name: {"content": "bar"}}}}}

            md = cfn_helper.Metadata('teststack', None)
            self.assertTrue(
                md.retrieve(meta_str=md_data, last_path=self.last_file))
            md.cfn_init()
            self.assertThat(foo_file.name, ttm.FileContains('bar'))

    def test_cfn_init_with_ignore_errors_false(self):
        self.mock_cmd_run(['su', 'root', '-c', '/bin/command1']).AndReturn(
            FakePOpen('Doing something', 'error', -1))
        self.m.ReplayAll()

        md_data = {"AWS::CloudFormation::Init": {"config": {"commands": {
            "00_foo": {"command": "/bin/command1",
                       "ignoreErrors": "false"}}}}}

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(
            md.retrieve(meta_str=md_data, last_path=self.last_file))
        self.assertRaises(cfn_helper.CommandsHandlerRunError, md.cfn_init)

    def test_cfn_init_with_ignore_errors_true(self):
        self.mock_cmd_run(['su', 'root', '-c', '/bin/command1']).AndReturn(
            FakePOpen('Doing something', 'error', -1))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/command2']).AndReturn(
            FakePOpen('All good'))
        self.m.ReplayAll()

        md_data = {"AWS::CloudFormation::Init": {"config": {"commands": {
            "00_foo": {"command": "/bin/command1",
                       "ignoreErrors": "true"},
            "01_bar": {"command": "/bin/command2",
                       "ignoreErrors": "false"}
        }}}}

        md = cfn_helper.Metadata('teststack', None)
        self.assertTrue(
            md.retrieve(meta_str=md_data, last_path=self.last_file))
        md.cfn_init()


class TestSourcesHandler(MockPopenTestCase):
    def test_apply_sources_empty(self):
        sh = cfn_helper.SourcesHandler({})
        sh.apply_sources()

    def _test_apply_sources(self, url, end_file):
        dest = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, dest)
        sources = {dest: url}
        td = os.path.dirname(end_file)
        self.m.StubOutWithMock(tempfile, 'mkdtemp')
        tempfile.mkdtemp().AndReturn(td)
        er = "mkdir -p '%s'; cd '%s'; curl -s '%s' | gunzip | tar -xvf -"
        cmd = ['su', 'root', '-c',
               er % (dest, dest, url)]
        self.mock_cmd_run(cmd).AndReturn(FakePOpen('Curl good'))
        self.m.ReplayAll()
        sh = cfn_helper.SourcesHandler(sources)
        sh.apply_sources()

    def test_apply_sources_github(self):
        url = "https://github.com/NoSuchProject/tarball/NoSuchTarball"
        td = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, td)
        end_file = '%s/NoSuchProject-NoSuchTarball.tar.gz' % td
        self._test_apply_sources(url, end_file)

    def test_apply_sources_general(self):
        url = "https://website.no.existe/a/b/c/file.tar.gz"
        td = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, td)
        end_file = '%s/file.tar.gz' % td
        self._test_apply_sources(url, end_file)

    def test_apply_source_cmd(self):
        sh = cfn_helper.SourcesHandler({})
        er = "mkdir -p '%s'; cd '%s'; curl -s '%s' | %s | tar -xvf -"
        dest = '/tmp'
        # test tgz
        url = 'http://www.example.com/a.tgz'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "gunzip"), cmd)
        # test tar.gz
        url = 'http://www.example.com/a.tar.gz'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "gunzip"), cmd)
        # test github - tarball 1
        url = 'https://github.com/openstack/heat-cfntools/tarball/master'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "gunzip"), cmd)
        # test github - tarball 2
        url = 'https://github.com/openstack/heat-cfntools/tarball/master/'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "gunzip"), cmd)
        # test tbz2
        url = 'http://www.example.com/a.tbz2'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "bunzip2"), cmd)
        # test tar.bz2
        url = 'http://www.example.com/a.tar.bz2'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "bunzip2"), cmd)
        # test zip
        er = "mkdir -p '%s'; cd '%s'; curl -s -o '%s' '%s' && unzip -o '%s'"
        url = 'http://www.example.com/a.zip'
        d = "/tmp/tmp2I0yNK"
        tmp = "%s/a.zip" % d
        self.m.StubOutWithMock(tempfile, 'mkdtemp')
        tempfile.mkdtemp().AndReturn(d)
        self.m.ReplayAll()
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, tmp, url, tmp), cmd)
        # test gz
        er = "mkdir -p '%s'; cd '%s'; curl -s '%s' | %s > '%s'"
        url = 'http://www.example.com/a.sh.gz'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "gunzip", "a.sh"), cmd)
        # test bz2
        url = 'http://www.example.com/a.sh.bz2'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual(er % (dest, dest, url, "bunzip2", "a.sh"), cmd)
        # test other
        url = 'http://www.example.com/a.sh'
        cmd = sh._apply_source_cmd(dest, url)
        self.assertEqual("", cmd)
