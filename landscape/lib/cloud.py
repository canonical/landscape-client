from landscape.lib.fetch import fetch_async

EC2_HOST = "169.254.169.254"
EC2_API = "http://%s/latest" % (EC2_HOST,)
MAX_LENGTH = 64


def fetch_ec2_meta_data(fetch=None):
    """Fetch EC2 information about the cloud instance.

    The fetch parameter provided above is for non-mocked testing purposes.
    """
    cloud_data = []
    # We're not using a DeferredList here because we want to keep the
    # number of connections to the backend minimal. See lp:567515.
    deferred = _fetch_ec2_item("instance-id", cloud_data, fetch)
    deferred.addCallback(
        lambda ignore: _fetch_ec2_item("instance-type", cloud_data, fetch))
    deferred.addCallback(
        lambda ignore: _fetch_ec2_item("ami-id", cloud_data, fetch))

    def return_result(ignore):
        """Record the instance data returned by the EC2 API."""

        def _process_result(value):
            if value is not None:
                if isinstance(value, bytes):
                    value = value.decode("utf-8")
                return value[:MAX_LENGTH]

        (instance_id, instance_type, ami_id) = cloud_data
        return {
            "instance-id": _process_result(instance_id),
            "ami-id": _process_result(ami_id),
            "instance-type": _process_result(instance_type)}
    deferred.addCallback(return_result)
    return deferred


def _fetch_ec2_item(path, accumulate, fetch=None):
    """
     Get data at C{path} on the EC2 API endpoint, and add the result to the
    C{accumulate} list. The C{fetch} parameter is provided for testing only.
    """
    url = EC2_API + "/meta-data/" + path
    if fetch is None:
        fetch = fetch_async
    return fetch(url, follow=False).addCallback(accumulate.append)
