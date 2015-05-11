=========================
Heat CloudFormation Tools
=========================

There are several bootstrap methods for cloudformations:

1. Create image with application ready to go
2. Use cloud-init to run a startup script passed as userdata to the nova
   server create
3. Use the CloudFormation instance helper scripts

This package contains files required for choice #3.

cfn-init   -
             Reads the AWS::CloudFormation::Init for the instance resource,
             installs packages, and starts services
cfn-signal -
             Waits for an application to be ready before continuing, ie:
             supporting the WaitCondition feature
cfn-hup    -
             Handle updates from the UpdateStack CloudFormation API call

* Free software: Apache license
* Source: http://git.openstack.org/cgit/openstack/heat-cfntools
* Bugs: http://bugs.launchpad.net/heat-cfntools

Related projects
----------------
* http://wiki.openstack.org/Heat
