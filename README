[![Build Status](https://github.com/CanonicalLtd/landscape-client/actions/workflows/ci.yml/badge.svg)](https://github.com/CanonicalLtd/landscape-client/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/CanonicalLtd/landscape-client/branch/master/graph/badge.svg)](https://codecov.io/gh/CanonicalLtd/landscape-client)

## Installation Instructions

Add our beta PPA to get the latest updates to the landscape-client package

#### Add repo to an Ubuntu series 
```
sudo add-apt-repository ppa:landscape/self-hosted-beta
```

#### Add repo to a Debian based series that is not Ubuntu (experimental)

```
# 1. Install our signing key
gpg --keyserver keyserver.ubuntu.com --recv-keys 6e85a86e4652b4e6
gpg --export 6e85a86e4652b4e6 | sudo tee -a /usr/share/keyrings/landscape-client-keyring.gpg > /dev/null

# 2. Add repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/landscape-client-keyring.gpg] https://ppa.launchpadcontent.net/landscape/self-hosted-beta/ubuntu focal main" | sudo tee -a /etc/apt/sources.list.d/landscape-client.list
```

#### Install the package
```
sudo apt update && sudo apt install landscape-client
```

## Non-root mode

The Landscape Client generally runs as a combination of the `root` and
`landscape` users.  It is possible to disable the administrative features of
Landscape and run only the monitoring parts of it without using the `root`
user at all.

If you wish to use the Landscape Client in this way, it's recommended that you
perform these steps immediately after installing the landscape-client package.

Edit `/etc/default/landscape-client` and add the following lines:

```
RUN=1
DAEMON_USER=landscape
```

Edit `/etc/landscape/client.conf` and add the following line:
```
monitor_only = true
```

## Running

Now you can complete the configuration of your client and register with the 
Landscape service. There are two ways to do this:

1. `sudo landscape-config` and answer interactive prompts to finalize your configuration
2. `sudo landscape-config --account-name standalone --url https://<server>/message-system --ping-url http://<server>/ping` if registering to a self-hosted Landscape instance. Replace `<server>` with the hostname of your self-hosted Landscape instance.

## Developing

To run the full test suite, run the following command:

```
make check
```

When you want to test the landscape client manually without management
features, you can simply run:

```
$ ./scripts/landscape-client
```

This defaults to the `landscape-client.conf` configuration file.

When you want to test management features manually, you'll need to run as root.
There's a configuration file `root-client.conf` which specifies use of the
system bus.

```
$ sudo ./scripts/landscape-client -c root-client.conf
```

Before opening a PR, make sure to run the full testsuite and lint
```
make check3
make lint
```
