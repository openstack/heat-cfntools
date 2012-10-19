"""
This is a Glance interface that serves as a compatibility layer for python-
glance (used in Essex) and python-glanceclient (Folsom), which have very
different APIs.

Once we stop supporting Essex, this should be removed.
"""

import logging

__all__ = [
    'client',
    'get_image',
    'find_image_by_name',
    'create_image',
    'delete_image',
    'register_image',
    'ConnectionError',
    'NotFoundError',
    'AuthError',
]


def get_glance_client_essex(options):
    """
    Returns a new Glance client connection based on the passed options.
    """
    creds = dict(username=options.username,
                 password=options.password,
                 tenant=options.tenant,
                 auth_url=options.auth_url,
                 strategy=options.auth_strategy)

    # When neither host nor port are specified and we're using Keystone auth,
    # let it tell us the Glance entrypoint
    configure_via_auth = (options.auth_strategy == 'keystone' and
                          not (options.glance_host or options.glance_port))

    # NOTE: these are ignored by the client when `configure_via_auth` is True
    glance_host = options.glance_host if options.glance_host else '0.0.0.0'
    try:
        glance_port = int(options.glance_port) if options.glance_port else 9292
    except:
        logging.error('Port must be a number.')
        sys.exit(1)

    if configure_via_auth:
        logging.debug('Using Glance entry point received by Keystone.')
    else:
        logging.debug('Connecting to Glance at host: %s, port: %d' %
                      (glance_host, glance_port))

    client = GlanceClient(host=glance_host,
                                  port=glance_port,
                                  use_ssl=False,
                                  auth_tok=None,
                                  configure_via_auth=configure_via_auth,
                                  creds=creds)
    return client


def get_glance_client_folsom(options):
    creds = dict(username=options.username,
                 password=options.password,
                 tenant_name=options.tenant,
                 auth_url=options.auth_url)
    import keystoneclient.v2_0.client
    kc = keystoneclient.v2_0.client.Client(**creds)
    glance_url = kc.service_catalog.url_for(service_type='image',
                                            endpoint_type='publicURL')
    auth_token = kc.auth_token
    client = GlanceClient(1, glance_url, token=auth_token)
    return client


def get_image_essex(client, image_id):
    return client.get_image(image_id)


def get_image_folsom(client, image_id):
    return client.images.get(image_id)


def find_image_essex(client, image_name):
    """
    Looks up the image of a given name in Glance.

    Returns the image metadata or None if no image is found.
    """
    images = client.get_images(filters={'name': image_name})
    if images:
        return images[0]
    else:
        return None


def find_image_folsom(client, image_name):
    images = client.images.list(filters={'name': image_name})
    try:
        return images.next()
    except StopIteration:
        return None


def delete_image_essex(client, image):
    return client.delete_image(image['id'])


def delete_image_folsom(client, image):
    return client.images.delete(image)


def create_image_essex(client, image_meta, image_file):
    return client.add_image(image_meta, image_file)


def create_image_folsom(client, image_meta, image_file):
    image_meta['data'] = image_file
    image = client.images.create(**image_meta)
    return vars(image)


def register_image(client, qcow2_path, name, owner, existing_image):
    """
    Register the given image with Glance.
    """
    image_meta = {'name': name,
                  'is_public': True,
                  'disk_format': 'qcow2',
                  'min_disk': 0,
                  'min_ram': 0,
                  'owner': owner,
                  'container_format': 'bare'}

    if existing_image:
        delete_image(client, existing_image)

    with open(qcow2_path) as ifile:
        image_meta = create_image(client, image_meta, ifile)
    image_id = image_meta['id']
    logging.debug(" Added new image with ID: %s" % image_id)
    logging.debug(" Returned the following metadata for the new image:")
    for k, v in sorted(image_meta.items()):
        logging.debug(" %(k)30s => %(v)s" % locals())
    return image_id


try:
    import glanceclient
    from glanceclient.client import Client as GlanceClient
    from glanceclient.exc import CommunicationError as ConnectionError
    from glanceclient.exc import HTTPNotFound as NotFoundError
    from glanceclient.exc import HTTPUnauthorized as AuthError
    import keystoneclient.v2_0.client
    client = get_glance_client_folsom
    get_image = get_image_folsom
    find_image_by_name = find_image_folsom
    create_image = create_image_folsom
    delete_image = delete_image_folsom
except ImportError:
    import glance
    from glance.client import Client as GlanceClient
    from glance.common.exception import ClientConnectionError as ConnectionError
    from glance.common.exception import NotFound as NotFoundError
    from glance.common.exception import NotAuthenticated as AuthError
    client = get_glance_client_essex
    get_image = get_image_essex
    find_image_by_name = find_image_essex
    create_image = create_image_essex
    delete_image = delete_image_essex
