/*

 Copyright (c) 2011 Canonical, Ltd.

*/

#define _GNU_SOURCE
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <grp.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <pwd.h>

int main(int argc, char *argv[], char *envp[])
{
  char *apt_argv[] = {"/usr/bin/apt-get", "-q", "update", NULL};
  char *apt_envp[] = {"PATH=/bin:/usr/bin", NULL, NULL, NULL, NULL};

  // Set the HOME environment variable
  struct passwd *pwd = getpwuid(geteuid());
  if (!pwd) {
    fprintf(stderr, "error: Unable to find passwd entry for uid %d (%s)\n",
            geteuid(), strerror(errno));
    exit(1);
  }
  if (asprintf(&apt_envp[1], "HOME=%s", pwd->pw_dir) == -1) {
    perror("error: Unable to create HOME environment variable");
    exit(1);
  }

  // Pass proxy environment variables
  int proxy_arg = 2;
  char *http_proxy = getenv("http_proxy");
  if (http_proxy) {
      if (asprintf(&apt_envp[proxy_arg], "http_proxy=%s", http_proxy) == -1) {
        perror("error: Unable to set http_proxy environment variable");
        exit(1);
      }
      proxy_arg++;
  }
  char *https_proxy = getenv("https_proxy");
  if (https_proxy) {
      if (asprintf(&apt_envp[proxy_arg], "https_proxy=%s", https_proxy) == -1) {
        perror("error: Unable to set https_proxy environment variable");
        exit(1);
      }
  }

  // Drop any supplementary group
  if (setgroups(0, NULL) == -1) {
    perror("error: Unable to set supplementary groups IDs");
    exit(1);
  }

  // Set real/effective gid and uid
  if (setregid(pwd->pw_gid, pwd->pw_gid) == -1) {
    fprintf(stderr, "error: Unable to set real and effective gid (%s)\n",
            strerror(errno));
    exit(1);
  }
  if (setreuid(pwd->pw_uid, pwd->pw_uid) == -1) {
    perror("error: Unable to set real and effective uid");
    exit(1);
  }

  // Close all file descriptors except the standard ones
  struct rlimit rlp;
  if (getrlimit(RLIMIT_NOFILE, &rlp) == -1) {
    perror("error: Unable to determine file descriptor limits");
    exit(1);
  }
  int file_max;
  if (rlp.rlim_max == RLIM_INFINITY || rlp.rlim_max > 4096)
    file_max = 4096;
  else
    file_max = rlp.rlim_max;
  int file;
  for (file = 3; file < file_max; file++) {
    close(file);
  }

  // Set umask to 022
  umask(S_IWGRP | S_IWOTH);

  if (chdir("/") == -1) {
    perror("error: Unable to change working directory");
    exit(1);
  }

  // Run apt-get update
  execve(apt_argv[0], apt_argv, apt_envp);
  perror("error: Unable to execute apt-get");
  return 1;
}
