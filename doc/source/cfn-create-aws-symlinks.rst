=======================
cfn-create-aws-symlinks
=======================

.. program:: cfn-create-aws-symlinks

SYNOPSIS
========

``cfn-create-aws-symlinks``

DESCRIPTION
===========
Creates symlinks for the cfn-* scripts in this directory to /opt/aws/bin


OPTIONS
=======
.. cmdoption:: -t, --target

  Target directory to create symlinks, defaults to /opt/aws/bin

.. cmdoption:: -s, --source

  Source directory to create symlinks from. Defaults to the directory where this script is

.. cmdoption:: -f, --force

  If specified, will create symlinks even if there is already a target file


BUGS
====
Heat bugs are managed through Launchpad <https://launchpad.net/heat-cfntools>