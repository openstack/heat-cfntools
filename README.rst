====
HEAT
====

This is the beginings of an OpenStack project that provides a programmable
interface to orchestrate multiple cloud applications implementing well
known standards such as CloudFormation and TOSCA.

Currently we are focusing on CloudFormation but are watching the development
of the TOSCA specification.

Why heat? It makes the clouds raise and keeps them there.

Quick Start
-----------

If you'd like to run from the master branch, you can clone the git repo:

    git clone git@github.com:heat-api/heat.git


Install Heat by running::

    sudo python setup.py install

try:
shell1:

    heat-api

shell2:

    sudo heat-engine

shell3:

    heat create my_stack --template-url=https://raw.github.com/heat-api/heat/master/templates/WordPress_Single_Instance.template
References
----------
* http://docs.amazonwebservices.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html
* http://docs.amazonwebservices.com/AWSCloudFormation/latest/UserGuide/create-stack.html
* http://docs.amazonwebservices.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html
* http://www.oasis-open.org/committees/tc_home.php?wg_abbrev=tosca

Related projects
----------------
* http://wiki.openstack.org/Donabe
* http://wiki.openstack.org/DatabaseAsAService (could be used to provide AWS::RDS::DBInstance)
* http://wiki.openstack.org/QueueService (could be used to provide AWS::SQS::Queue)
