import logging
from landscape.lib.fetch import fetch_async

EC2_HOST = "169.254.169.254"
EC2_API = "http://%s/latest" % (EC2_HOST,)
METADATA_RETRY_MAX = 3  # Number of retries to get EC2 meta-data


def fetch_ec2_item(path, accumulate, fetch=None):
    """
     Get data at C{path} on the EC2 API endpoint, and add the result to the
    C{accumulate} list.
    """
    url = EC2_API + "/meta-data/" + path
    if fetch is None:
        fetch = fetch_async
    return fetch(url).addCallback(accumulate.append)


def fetch_ec2_meta_data(fetch=None):
    """Fetch EC2 information about the cloud instance."""
    cloud_data = []
    # We're not using a DeferredList here because we want to keep the
    # number of connections to the backend minimal. See lp:567515.
    logging.info("Querying cloud meta-data.")
    deferred = fetch_ec2_item("instance-id", cloud_data, fetch)
    deferred.addCallback(
        lambda ignore: fetch_ec2_item("instance-type", cloud_data, fetch))
    deferred.addCallback(
        lambda ignore: fetch_ec2_item("ami-id", cloud_data, fetch))

    def return_result(ignore):
        """Record the instance data returned by the EC2 API."""

        def _unicode_none(value):
            if value is None:
                return None
            else:
                return value.decode("utf-8")

        logging.info("Acquired cloud meta-data.")
        (instance_id, instance_type, ami_id) = cloud_data
        return {
            "instance-id": _unicode_none(instance_id),
            "ami-id": _unicode_none(ami_id),
            "instance-type": _unicode_none(instance_type)}
    
    deferred.addCallback(return_result)
    return deferred
