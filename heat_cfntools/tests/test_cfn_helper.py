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

import json
import os
import tempfile
from unittest import mock

import boto.cloudformation as cfn
import fixtures
import testtools
import testtools.matchers as ttm

from heat_cfntools.cfntools import cfn_helper


def popen_root_calls(calls, shell=False):
    kwargs = {'env': None, 'cwd': None, 'stderr': -1, 'stdout': -1,
              'shell': shell}
    return [
        mock.call(call, **kwargs)
        for call in calls
    ]


class FakePOpen(object):
    def __init__(self, stdout='', stderr='', returncode=0):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def communicate(self):
        return (self.stdout, self.stderr)

    def wait(self):
        pass


@mock.patch.object(cfn_helper.pwd, 'getpwnam')
@mock.patch.object(cfn_helper.os, 'seteuid')
@mock.patch.object(cfn_helper.os, 'geteuid')
class TestCommandRunner(testtools.TestCase):

    def test_command_runner(self, mock_geteuid, mock_seteuid, mock_getpwnam):
        def returns(*args, **kwargs):
            if args[0][0] == '/bin/command1':
                return FakePOpen('All good')
            elif args[0][0] == '/bin/command2':
                return FakePOpen('Doing something', 'error', -1)
            else:
                raise Exception('This should never happen')

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = returns
            cmd2 = cfn_helper.CommandRunner(['/bin/command2'])
            cmd1 = cfn_helper.CommandRunner(['/bin/command1'],
                                            nextcommand=cmd2)
            cmd1.run('root')
            self.assertEqual(
                'CommandRunner:\n\tcommand: [\'/bin/command1\']\n\tstdout: '
                'All good',
                str(cmd1))
            self.assertEqual(
                'CommandRunner:\n\tcommand: [\'/bin/command2\']\n\tstatus: '
                '-1\n\tstdout: Doing something\n\tstderr: error',
                str(cmd2))
            calls = popen_root_calls([['/bin/command1'], ['/bin/command2']])
            mock_popen.assert_has_calls(calls)

    def test_privileges_are_lowered_for_non_root_user(self, mock_geteuid,
                                                      mock_seteuid,
                                                      mock_getpwnam):
        pw_entry = mock.Mock()
        pw_entry.pw_uid = 1001
        mock_getpwnam.return_value = pw_entry
        mock_geteuid.return_value = 0
        calls = [mock.call(1001), mock.call(0)]
        with mock.patch('subprocess.Popen') as mock_popen:
            command = ['/bin/command', '--option=value', 'arg1', 'arg2']
            cmd = cfn_helper.CommandRunner(command)
            cmd.run(user='nonroot')
            self.assertTrue(mock_geteuid.called)
            mock_getpwnam.assert_called_once_with('nonroot')
            mock_seteuid.assert_has_calls(calls)
            self.assertTrue(mock_popen.called)

    def test_run_returns_when_cannot_set_privileges(self, mock_geteuid,
                                                    mock_seteuid,
                                                    mock_getpwnam):
        msg = '[Error 1] Permission Denied'
        mock_seteuid.side_effect = Exception(msg)
        with mock.patch('subprocess.Popen') as mock_popen:
            command = ['/bin/command2']
            cmd = cfn_helper.CommandRunner(command)
            cmd.run(user='nonroot')
            self.assertTrue(mock_getpwnam.called)
            self.assertTrue(mock_seteuid.called)
            self.assertFalse(mock_popen.called)
            self.assertEqual(126, cmd.status)
            self.assertEqual(msg, cmd.stderr)

    def test_privileges_are_restored_for_command_failure(self, mock_geteuid,
                                                         mock_seteuid,
                                                         mock_getpwnam):
        pw_entry = mock.Mock()
        pw_entry.pw_uid = 1001
        mock_getpwnam.return_value = pw_entry
        mock_geteuid.return_value = 0
        calls = [mock.call(1001), mock.call(0)]
        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = ValueError('Something wrong')
            command = ['/bin/command', '--option=value', 'arg1', 'arg2']
            cmd = cfn_helper.CommandRunner(command)
            self.assertRaises(ValueError, cmd.run, user='nonroot')
            self.assertTrue(mock_geteuid.called)
            mock_getpwnam.assert_called_once_with('nonroot')
            mock_seteuid.assert_has_calls(calls)
            self.assertTrue(mock_popen.called)


@mock.patch.object(cfn_helper, 'controlled_privileges')
class TestPackages(testtools.TestCase):

    def test_yum_install(self, mock_cp):

        def returns(*args, **kwargs):
            if args[0][0] == 'rpm' and args[0][1] == '-q':
                return FakePOpen(returncode=1)
            else:
                return FakePOpen(returncode=0)

        calls = [['which', 'yum']]
        for pack in ('httpd', 'wordpress', 'mysql-server'):
            calls.append(['rpm', '-q', pack])
            calls.append(['yum', '-y', '--showduplicates', 'list',
                          'available', pack])
        calls = popen_root_calls(calls)

        packages = {
            "yum": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = returns
            cfn_helper.PackagesHandler(packages).apply_packages()
            mock_popen.assert_has_calls(calls, any_order=True)

    def test_dnf_install_yum_unavailable(self, mock_cp):

        def returns(*args, **kwargs):
            if ((args[0][0] == 'rpm' and args[0][1] == '-q')
                    or (args[0][0] == 'which' and args[0][1] == 'yum')):
                return FakePOpen(returncode=1)
            else:
                return FakePOpen(returncode=0)

        calls = [['which', 'yum']]
        for pack in ('httpd', 'wordpress', 'mysql-server'):
            calls.append(['rpm', '-q', pack])
            calls.append(['dnf', '-y', '--showduplicates', 'list',
                          'available', pack])
        calls = popen_root_calls(calls)

        packages = {
            "yum": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = returns
            cfn_helper.PackagesHandler(packages).apply_packages()
            mock_popen.assert_has_calls(calls, any_order=True)

    def test_dnf_install(self, mock_cp):

        def returns(*args, **kwargs):
            if args[0][0] == 'rpm' and args[0][1] == '-q':
                return FakePOpen(returncode=1)
            else:
                return FakePOpen(returncode=0)

        calls = []
        for pack in ('httpd', 'wordpress', 'mysql-server'):
            calls.append(['rpm', '-q', pack])
            calls.append(['dnf', '-y', '--showduplicates', 'list',
                          'available', pack])
        calls = popen_root_calls(calls)

        packages = {
            "dnf": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = returns
            cfn_helper.PackagesHandler(packages).apply_packages()
            mock_popen.assert_has_calls(calls, any_order=True)

    def test_zypper_install(self, mock_cp):

        def returns(*args, **kwargs):
            if args[0][0].startswith('rpm') and args[0][1].startswith('-q'):
                return FakePOpen(returncode=1)
            else:
                return FakePOpen(returncode=0)

        calls = []
        for pack in ('httpd', 'wordpress', 'mysql-server'):
            calls.append(['rpm', '-q', pack])
            calls.append(['zypper', '-n', '--no-refresh', 'search', pack])
        calls = popen_root_calls(calls)

        packages = {
            "zypper": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = returns
            cfn_helper.PackagesHandler(packages).apply_packages()
            mock_popen.assert_has_calls(calls, any_order=True)

    def test_apt_install(self, mock_cp):
        packages = {
            "apt": {
                "mysql-server": [],
                "httpd": [],
                "wordpress": []
            }
        }

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = FakePOpen(returncode=0)
            cfn_helper.PackagesHandler(packages).apply_packages()
            self.assertTrue(mock_popen.called)


@mock.patch.object(cfn_helper, 'controlled_privileges')
class TestServicesHandler(testtools.TestCase):

    def test_services_handler_systemd(self, mock_cp):
        calls = []
        returns = []

        # apply_services
        calls.append(['/bin/systemctl', 'enable', 'httpd.service'])
        returns.append(FakePOpen())
        calls.append(['/bin/systemctl', 'status', 'httpd.service'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/bin/systemctl', 'start', 'httpd.service'])
        returns.append(FakePOpen())
        calls.append(['/bin/systemctl', 'enable', 'mysqld.service'])
        returns.append(FakePOpen())
        calls.append(['/bin/systemctl', 'status', 'mysqld.service'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/bin/systemctl', 'start', 'mysqld.service'])
        returns.append(FakePOpen())

        # monitor_services not running
        calls.append(['/bin/systemctl', 'status', 'httpd.service'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/bin/systemctl', 'start', 'httpd.service'])
        returns.append(FakePOpen())

        calls = popen_root_calls(calls)

        calls.extend(popen_root_calls(['/bin/services_restarted'], shell=True))
        returns.append(FakePOpen())

        calls.extend(popen_root_calls([['/bin/systemctl', 'status',
                                        'mysqld.service']]))
        returns.append(FakePOpen(returncode=-1))
        calls.extend(popen_root_calls([['/bin/systemctl', 'start',
                                        'mysqld.service']]))
        returns.append(FakePOpen())

        calls.extend(popen_root_calls(['/bin/services_restarted'], shell=True))
        returns.append(FakePOpen())

        # monitor_services running
        calls.extend(popen_root_calls([['/bin/systemctl', 'status',
                                        'httpd.service']]))
        returns.append(FakePOpen())
        calls.extend(popen_root_calls([['/bin/systemctl', 'status',
                                        'mysqld.service']]))
        returns.append(FakePOpen())

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

        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.side_effect = returns

                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                # services not running
                sh.monitor_services()

                # services running
                sh.monitor_services()
                mock_popen.assert_has_calls(calls, any_order=True)
            mock_exists.assert_called_with('/bin/systemctl')

    def test_services_handler_systemd_disabled(self, mock_cp):
        calls = []

        # apply_services
        calls.append(['/bin/systemctl', 'disable', 'httpd.service'])
        calls.append(['/bin/systemctl', 'status', 'httpd.service'])
        calls.append(['/bin/systemctl', 'stop', 'httpd.service'])
        calls.append(['/bin/systemctl', 'disable', 'mysqld.service'])
        calls.append(['/bin/systemctl', 'status', 'mysqld.service'])
        calls.append(['/bin/systemctl', 'stop', 'mysqld.service'])
        calls = popen_root_calls(calls)

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
        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.return_value = FakePOpen()
                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                mock_popen.assert_has_calls(calls, any_order=True)
            mock_exists.assert_called_with('/bin/systemctl')

    def test_services_handler_sysv_service_chkconfig(self, mock_cp):

        def exists(*args, **kwargs):
            return args[0] != '/bin/systemctl'

        calls = []
        returns = []

        # apply_services
        calls.append(['/sbin/chkconfig', 'httpd', 'on'])
        returns.append(FakePOpen())
        calls.append(['/sbin/service', 'httpd', 'status'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/sbin/service', 'httpd', 'start'])
        returns.append(FakePOpen())

        # monitor_services not running
        calls.append(['/sbin/service', 'httpd', 'status'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/sbin/service', 'httpd', 'start'])
        returns.append(FakePOpen())

        calls = popen_root_calls(calls)

        calls.extend(popen_root_calls(['/bin/services_restarted'], shell=True))
        returns.append(FakePOpen())

        # monitor_services running
        calls.extend(popen_root_calls([['/sbin/service', 'httpd', 'status']]))
        returns.append(FakePOpen())

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

        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = exists
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.side_effect = returns
                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                # services not running
                sh.monitor_services()

                # services running
                sh.monitor_services()
                mock_popen.assert_has_calls(calls)
            mock_exists.assert_any_call('/bin/systemctl')
            mock_exists.assert_any_call('/sbin/service')
            mock_exists.assert_any_call('/sbin/chkconfig')

    def test_services_handler_sysv_disabled_service_chkconfig(self, mock_cp):
        def exists(*args, **kwargs):
            return args[0] != '/bin/systemctl'

        calls = []

        # apply_services
        calls.append(['/sbin/chkconfig', 'httpd', 'off'])
        calls.append(['/sbin/service', 'httpd', 'status'])
        calls.append(['/sbin/service', 'httpd', 'stop'])

        calls = popen_root_calls(calls)

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

        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = exists
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.return_value = FakePOpen()
                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                mock_popen.assert_has_calls(calls)
            mock_exists.assert_any_call('/bin/systemctl')
            mock_exists.assert_any_call('/sbin/service')
            mock_exists.assert_any_call('/sbin/chkconfig')

    def test_services_handler_sysv_systemctl(self, mock_cp):
        calls = []
        returns = []

        # apply_services
        calls.append(['/bin/systemctl', 'enable', 'httpd.service'])
        returns.append(FakePOpen())
        calls.append(['/bin/systemctl', 'status', 'httpd.service'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/bin/systemctl', 'start', 'httpd.service'])
        returns.append(FakePOpen())

        # monitor_services not running
        calls.append(['/bin/systemctl', 'status', 'httpd.service'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/bin/systemctl', 'start', 'httpd.service'])
        returns.append(FakePOpen())

        shell_calls = []
        shell_calls.append('/bin/services_restarted')
        returns.append(FakePOpen())

        calls = popen_root_calls(calls)
        calls.extend(popen_root_calls(shell_calls, shell=True))

        # monitor_services running
        calls.extend(popen_root_calls([['/bin/systemctl', 'status',
                                        'httpd.service']]))
        returns.append(FakePOpen())

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

        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.side_effect = returns
                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                # services not running
                sh.monitor_services()

                # services running
                sh.monitor_services()
                mock_popen.assert_has_calls(calls)
            mock_exists.assert_called_with('/bin/systemctl')

    def test_services_handler_sysv_disabled_systemctl(self, mock_cp):
        calls = []

        # apply_services
        calls.append(['/bin/systemctl', 'disable', 'httpd.service'])
        calls.append(['/bin/systemctl', 'status', 'httpd.service'])
        calls.append(['/bin/systemctl', 'stop', 'httpd.service'])

        calls = popen_root_calls(calls)

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

        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.return_value = FakePOpen()
                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                mock_popen.assert_has_calls(calls)
            mock_exists.assert_called_with('/bin/systemctl')

    def test_services_handler_sysv_service_updaterc(self, mock_cp):
        calls = []
        returns = []

        # apply_services
        calls.append(['/usr/sbin/update-rc.d', 'httpd', 'enable'])
        returns.append(FakePOpen())
        calls.append(['/usr/sbin/service', 'httpd', 'status'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/usr/sbin/service', 'httpd', 'start'])
        returns.append(FakePOpen())

        # monitor_services not running
        calls.append(['/usr/sbin/service', 'httpd', 'status'])
        returns.append(FakePOpen(returncode=-1))
        calls.append(['/usr/sbin/service', 'httpd', 'start'])
        returns.append(FakePOpen())

        shell_calls = []
        shell_calls.append('/bin/services_restarted')
        returns.append(FakePOpen())

        calls = popen_root_calls(calls)
        calls.extend(popen_root_calls(shell_calls, shell=True))

        # monitor_services running
        calls.extend(popen_root_calls([['/usr/sbin/service', 'httpd',
                                        'status']]))
        returns.append(FakePOpen())

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

        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.side_effect = returns
                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                # services not running
                sh.monitor_services()

                # services running
                sh.monitor_services()
                mock_popen.assert_has_calls(calls)
            mock_exists.assert_any_call('/bin/systemctl')
            mock_exists.assert_any_call('/sbin/service')
            mock_exists.assert_any_call('/sbin/chkconfig')

    def test_services_handler_sysv_disabled_service_updaterc(self, mock_cp):
        calls = []
        returns = []

        # apply_services
        calls.append(['/usr/sbin/update-rc.d', 'httpd', 'disable'])
        returns.append(FakePOpen())
        calls.append(['/usr/sbin/service', 'httpd', 'status'])
        returns.append(FakePOpen())
        calls.append(['/usr/sbin/service', 'httpd', 'stop'])
        returns.append(FakePOpen())

        calls = popen_root_calls(calls)

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

        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.side_effect = returns
                sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
                sh.apply_services()
                mock_popen.assert_has_calls(calls)
            mock_exists.assert_any_call('/bin/systemctl')
            mock_exists.assert_any_call('/sbin/service')
            mock_exists.assert_any_call('/sbin/chkconfig')


class TestHupConfig(testtools.TestCase):

    def test_load_main_section(self):
        fcreds = tempfile.NamedTemporaryFile()
        fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n'.encode('UTF-8'))
        fcreds.flush()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write(('''[main]
stack=teststack
credential-file=%s''' % fcreds.name).encode('UTF-8'))
        main_conf.flush()
        mainconfig = cfn_helper.HupConfig([open(main_conf.name)])
        self.assertEqual(
            '{stack: teststack, credential_file: %s, '
            'region: nova, interval:10}' % fcreds.name,
            str(mainconfig))
        main_conf.close()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write(('''[main]
stack=teststack
region=region1
credential-file=%s-invalid
interval=120''' % fcreds.name).encode('UTF-8'))
        main_conf.flush()
        e = self.assertRaises(cfn_helper.InvalidCredentialsException,
                              cfn_helper.HupConfig,
                              [open(main_conf.name)])
        self.assertIn('invalid credentials file', str(e))
        fcreds.close()

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_hup_config(self, mock_cp):
        hooks_conf = tempfile.NamedTemporaryFile()

        def write_hook_conf(f, name, triggers, path, action):
            f.write((
                '[%s]\ntriggers=%s\npath=%s\naction=%s\nrunas=root\n\n' % (
                    name, triggers, path, action)).encode('UTF-8'))

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
        fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n'.encode('UTF-8'))
        fcreds.flush()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write(('''[main]
stack=teststack
credential-file=%s
region=region1
interval=120''' % fcreds.name).encode('UTF-8'))
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

        calls = []
        calls.extend(popen_root_calls(['/bin/cfn-http-restarted'], shell=True))
        calls.extend(popen_root_calls(['/bin/hook1'], shell=True))
        calls.extend(popen_root_calls(['/bin/hook2'], shell=True))
        calls.extend(popen_root_calls(['/bin/hook3'], shell=True))

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = FakePOpen('All good')

            for hook in hooks:
                hook.event(hook.triggers, None, hook.resource_name_get())

            hooks_conf.close()
            fcreds.close()
            main_conf.close()
            mock_popen.assert_has_calls(calls)


class TestCfnHelper(testtools.TestCase):

    def _check_metadata_content(self, content, value):
        with tempfile.NamedTemporaryFile() as metadata_info:
            metadata_info.write(content.encode('UTF-8'))
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
        self.assertIsNone(cfn_helper.metadata_server_port(random_filename))

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

        with mock.patch.object(
            cfn.CloudFormationConnection, 'describe_stack_resource'
        ) as mock_dsr:
            mock_dsr.return_value = {
                'DescribeStackResourceResponse': {
                    'DescribeStackResourceResult': {
                        'StackResourceDetail': {'Metadata': md_data}}}}
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

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_nova_meta_curl(self, mock_cp):
        url = 'http://169.254.169.254/openstack/2012-08-10/meta_data.json'
        temp_home = tempfile.mkdtemp()
        cache_path = os.path.join(temp_home, 'meta_data.json')

        def cleanup_temp_home(thome):
            os.unlink(cache_path)
            os.rmdir(thome)

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
            return FakePOpen('Downloaded', '', 0)

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = write_cache_file
            md = cfn_helper.Metadata('teststack', None)
            meta_out = md.get_nova_meta(cache_path=cache_path)
            self.assertEqual(meta_in, meta_out)
            mock_popen.assert_has_calls(
                popen_root_calls([['curl', '-o', cache_path, url]]))

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_nova_meta_curl_corrupt(self, mock_cp):
        url = 'http://169.254.169.254/openstack/2012-08-10/meta_data.json'
        temp_home = tempfile.mkdtemp()
        cache_path = os.path.join(temp_home, 'meta_data.json')

        def cleanup_temp_home(thome):
            os.unlink(cache_path)
            os.rmdir(thome)

        self.addCleanup(cleanup_temp_home, temp_home)

        md_str = "this { is not really json"

        def write_cache_file(*params, **kwargs):
            with open(cache_path, 'w+') as cache_file:
                cache_file.write(md_str)
                cache_file.flush()
                self.assertThat(cache_file.name, ttm.FileContains(md_str))
            return FakePOpen('Downloaded', '', 0)

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = write_cache_file
            md = cfn_helper.Metadata('teststack', None)
            meta_out = md.get_nova_meta(cache_path=cache_path)
            self.assertIsNone(meta_out)
            mock_popen.assert_has_calls(
                popen_root_calls([['curl', '-o', cache_path, url]]))

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_nova_meta_curl_failed(self, mock_cp):
        url = 'http://169.254.169.254/openstack/2012-08-10/meta_data.json'
        temp_home = tempfile.mkdtemp()
        cache_path = os.path.join(temp_home, 'meta_data.json')

        def cleanup_temp_home(thome):
            os.rmdir(thome)

        self.addCleanup(cleanup_temp_home, temp_home)

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = FakePOpen('Failed', '', 1)
            md = cfn_helper.Metadata('teststack', None)
            meta_out = md.get_nova_meta(cache_path=cache_path)
            self.assertIsNone(meta_out)
            mock_popen.assert_has_calls(
                popen_root_calls([['curl', '-o', cache_path, url]]))

    def test_get_tags(self):
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

        with mock.patch.object(md, 'get_nova_meta') as mock_method:
            mock_method.return_value = md_data
            tags = md.get_tags()
            mock_method.assert_called_once_with()

        self.assertEqual(tags_expect, tags)

    def test_get_instance_id(self):
        uuid = "f9431d18-d971-434d-9044-5b38f5b4646f"
        md_data = {"uuid": uuid,
                   "availability_zone": "nova",
                   "hostname": "as-wikidatabase-4ykioj3lgi57.novalocal",
                   "launch_index": 0,
                   "public_keys": {"heat_key": "ssh-rsa etc...\n"},
                   "name": "as-WikiDatabase-4ykioj3lgi57"}

        md = cfn_helper.Metadata('teststack', None)

        with mock.patch.object(md, 'get_nova_meta') as mock_method:
            mock_method.return_value = md_data
            self.assertEqual(md.get_instance_id(), uuid)
            mock_method.assert_called_once_with()


class TestCfnInit(testtools.TestCase):

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

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_cfn_init_with_ignore_errors_false(self, mock_cp):
        md_data = {"AWS::CloudFormation::Init": {"config": {"commands": {
            "00_foo": {"command": "/bin/command1",
                       "ignoreErrors": "false"}}}}}
        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = FakePOpen('Doing something', 'error', -1)
            md = cfn_helper.Metadata('teststack', None)
            self.assertTrue(
                md.retrieve(meta_str=md_data, last_path=self.last_file))
            self.assertRaises(cfn_helper.CommandsHandlerRunError, md.cfn_init)
            mock_popen.assert_has_calls(popen_root_calls(['/bin/command1'],
                                                         shell=True))

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_cfn_init_with_ignore_errors_true(self, mock_cp):
        calls = []
        returns = []
        calls.extend(popen_root_calls(['/bin/command1'], shell=True))
        returns.append(FakePOpen('Doing something', 'error', -1))
        calls.extend(popen_root_calls(['/bin/command2'], shell=True))
        returns.append(FakePOpen('All good'))

        md_data = {"AWS::CloudFormation::Init": {"config": {"commands": {
            "00_foo": {"command": "/bin/command1",
                       "ignoreErrors": "true"},
            "01_bar": {"command": "/bin/command2",
                       "ignoreErrors": "false"}
        }}}}

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = returns
            md = cfn_helper.Metadata('teststack', None)
            self.assertTrue(
                md.retrieve(meta_str=md_data, last_path=self.last_file))
            md.cfn_init()
            mock_popen.assert_has_calls(calls)

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_cfn_init_runs_list_commands_without_shell(self, mock_cp):
        calls = []
        returns = []
        # command supplied as list shouldn't run on shell
        calls.extend(popen_root_calls([['/bin/command1', 'arg']], shell=False))
        returns.append(FakePOpen('Doing something'))
        # command supplied as string should run on shell
        calls.extend(popen_root_calls(['/bin/command2'], shell=True))
        returns.append(FakePOpen('All good'))

        md_data = {"AWS::CloudFormation::Init": {"config": {"commands": {
            "00_foo": {"command": ["/bin/command1", "arg"]},
            "01_bar": {"command": "/bin/command2"}
        }}}}

        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = returns
            md = cfn_helper.Metadata('teststack', None)
            self.assertTrue(
                md.retrieve(meta_str=md_data, last_path=self.last_file))
            md.cfn_init()
            mock_popen.assert_has_calls(calls)


class TestSourcesHandler(testtools.TestCase):
    def test_apply_sources_empty(self):
        sh = cfn_helper.SourcesHandler({})
        sh.apply_sources()

    def _test_apply_sources(self, url, end_file):
        dest = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, dest)
        sources = {dest: url}
        td = os.path.dirname(end_file)
        er = "mkdir -p '%s'; cd '%s'; curl -s '%s' | gunzip | tar -xvf -"
        calls = popen_root_calls([er % (dest, dest, url)], shell=True)

        with mock.patch.object(tempfile, 'mkdtemp') as mock_mkdtemp:
            mock_mkdtemp.return_value = td
            with mock.patch('subprocess.Popen') as mock_popen:
                mock_popen.return_value = FakePOpen('Curl good')
                sh = cfn_helper.SourcesHandler(sources)
                sh.apply_sources()
                mock_popen.assert_has_calls(calls)
            mock_mkdtemp.assert_called_with()

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_apply_sources_github(self, mock_cp):
        url = "https://github.com/NoSuchProject/tarball/NoSuchTarball"
        dest = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, dest)
        sources = {dest: url}
        er = "mkdir -p '%s'; cd '%s'; curl -s '%s' | gunzip | tar -xvf -"
        calls = popen_root_calls([er % (dest, dest, url)], shell=True)
        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = FakePOpen('Curl good')
            sh = cfn_helper.SourcesHandler(sources)
            sh.apply_sources()
            mock_popen.assert_has_calls(calls)

    @mock.patch.object(cfn_helper, 'controlled_privileges')
    def test_apply_sources_general(self, mock_cp):
        url = "https://website.no.existe/a/b/c/file.tar.gz"
        dest = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, dest)
        sources = {dest: url}
        er = "mkdir -p '%s'; cd '%s'; curl -s '%s' | gunzip | tar -xvf -"
        calls = popen_root_calls([er % (dest, dest, url)], shell=True)
        with mock.patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = FakePOpen('Curl good')
            sh = cfn_helper.SourcesHandler(sources)
            sh.apply_sources()
            mock_popen.assert_has_calls(calls)

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
        with mock.patch.object(tempfile, 'mkdtemp') as mock_mkdtemp:
            mock_mkdtemp.return_value = d

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
            mock_mkdtemp.assert_called_with()
